#!/usr/bin/env python3
"""Launch the fund engine with real market data, live analysis loop, and gRPC server.

Usage:
    python run_server.py                          # uses .env or env vars
    SUPABASE_URL=... SUPABASE_KEY=... python run_server.py

Requires SiliconDB running with beliefs and theme discovery enabled:
    python -m silicondb.server /path/to/db --enable-beliefs --enable-theme-discovery --port 8642
"""

import os
import queue
import sys
import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Ensure src/ is on path
sys.path.insert(0, str(Path(__file__).parent))

from fund.types import Fund, Instrument, WeeklyNAV
from fund.universe import InvestmentUniverse
from fund.journal import EventJournal
from fund.thermo_metrics import ThermoMetrics
from fund.benchmarks import BenchmarkEngine
from fund.heartbeat import HealthMonitor
from fund.supabase_sync import SupabaseSync, SupabaseConfig
from fund.grpc_runner import run_server
from fund.grpc_server import FundServiceServicer
from fund.live_engine import LiveEngine
from fund.broker_types import AlpacaConfig, StreamConfig, BrokerAccount, BrokerPosition, BrokerOrder
from fund.price_cache import PriceCache
from fund.stream_service import AlpacaStreamService
from fund.observation_recorder import ObservationRecorder
from fund.tempo import Tempo
from fund.reactor import Reactor, ReactorConfig


# ── Lightweight simulation broker (no API keys required) ─────────────────────

class _SimBroker:
    """In-memory broker for the run_server simulation script.

    Replaced MockBroker after that class was deleted. Provides only the subset
    of the AlpacaBroker interface used by sync_to_supabase and the main loop:
    get_account(), get_positions(), seed_position(), seed_price().
    """

    def __init__(self, cash: Decimal = Decimal("100000")) -> None:
        self._cash = cash
        self._positions: dict = {}  # symbol -> (qty, avg_entry_price)
        self._prices: dict = {}     # symbol -> Decimal

    def seed_price(self, symbol: str, price: Decimal) -> None:
        self._prices[symbol] = price

    def seed_position(self, symbol: str, qty: Decimal, avg_price: Decimal) -> None:
        self._positions[symbol] = (qty, avg_price)
        if symbol not in self._prices:
            self._prices[symbol] = avg_price

    def get_account(self) -> BrokerAccount:
        equity = self._cash + sum(
            qty * self._prices.get(sym, avg)
            for sym, (qty, avg) in self._positions.items()
        )
        return BrokerAccount(
            cash=self._cash,
            equity=equity,
            buying_power=self._cash,
            status="ACTIVE",
        )

    def get_positions(self) -> list:
        result = []
        for sym, (qty, avg) in self._positions.items():
            if qty <= 0:
                continue
            price = self._prices.get(sym, avg)
            mv = qty * price
            cost = qty * avg
            upl = mv - cost
            upl_pct = float(upl / cost) if cost else 0.0
            result.append(BrokerPosition(
                symbol=sym,
                quantity=qty,
                market_value=mv,
                avg_entry_price=avg,
                current_price=price,
                unrealized_pl=upl,
                unrealized_pl_pct=upl_pct,
            ))
        return result


# ── Null SiliconDB client (no-op for dev/test without SiliconDB running) ─────

class _NullSiliconDB:
    """Drop-in SiliconDB client that silently discards all calls.

    Used when SILICONDB_URL is not reachable or in development mode.
    """

    def add_observation(self, obs: dict) -> None:
        pass

    def record_observation_batch(self, observations: list) -> None:
        pass

    def propagate(self, **kwargs) -> None:
        pass

    def add_cooccurrences(self, **kwargs) -> None:
        pass

    def epistemic_briefing(self, **kwargs) -> None:
        pass

    def insert_triples(self, **kwargs) -> None:
        pass


# ── Null stream service (no-op when no Alpaca credentials are set) ────────────

class _NullStreamService:
    """Drop-in AlpacaStreamService for use when ALPACA_API_KEY is not set.

    Provides the minimal interface consumed by LiveEngine:
    is_running, dropped_events, _event_queue, start(), stop().
    """

    def __init__(self, event_queue: queue.Queue) -> None:
        self._event_queue = event_queue
        self.dropped_events: int = 0

    @property
    def is_running(self) -> bool:
        return False

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


# ── Portfolio definition ──────────────────────────────────────────────────────

PORTFOLIO_SYMBOLS = ["AAPL", "MSFT", "NVDA", "GOOG", "AMZN"]

# Shares held (starting position — a year ago)
HOLDINGS = {
    "AAPL": 50,
    "MSFT": 30,
    "NVDA": 25,
    "GOOG": 15,
    "AMZN": 20,
}

SEED_INSTRUMENTS = [
    Instrument("AAPL", "Apple Inc.", "equity", "Consumer tech dominance + services growth", "birger", date(2025, 1, 1), 5),
    Instrument("MSFT", "Microsoft Corp.", "equity", "Cloud + AI platform play", "birger", date(2025, 1, 1), 5),
    Instrument("NVDA", "NVIDIA Corp.", "equity", "GPU compute monopoly for AI training", "birger", date(2025, 1, 1), 4),
    Instrument("GOOG", "Alphabet Inc.", "equity", "Search moat + Waymo optionality", "birger", date(2025, 1, 1), 3),
    Instrument("AMZN", "Amazon.com", "equity", "AWS + retail logistics flywheel", "birger", date(2025, 1, 1), 4),
    Instrument("TSM", "Taiwan Semiconductor", "equity", "Foundry monopoly for advanced nodes", "birger", date(2025, 2, 1), 3),
    Instrument("META", "Meta Platforms", "equity", "Social graph + Reels monetisation", "birger", date(2025, 2, 1), 2),
]

STARTING_CASH = Decimal("25000")


# ── Fetch real historical data ────────────────────────────────────────────────

def fetch_real_weekly_history(symbols: dict, weeks: int = 52) -> tuple:
    """Fetch real weekly closing prices for the past year and build NAV history.

    Returns (nav_history, broker_with_current_prices)
    """
    import yfinance as yf

    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks + 1)

    print(f"  Fetching {weeks} weeks of data ({start_date} → {end_date})...")

    # Download all symbols at once for efficiency
    tickers = " ".join(symbols.keys())
    df = yf.download(tickers, start=start_date.isoformat(), end=end_date.isoformat(),
                     interval="1wk", progress=False)

    if df.empty:
        print("  WARNING: No data from Yahoo Finance, falling back to mock")
        return [], None

    # Handle MultiIndex columns from yfinance
    close = df["Close"]
    if hasattr(close, "columns"):
        # Multiple symbols
        pass
    else:
        # Single symbol edge case
        close = df[["Close"]]
        close.columns = [list(symbols.keys())[0]]

    # Build weekly NAV history from real prices
    history = []
    cash = float(STARTING_CASH)
    prev_nav = None
    hwm = 0.0

    for i, (idx, row) in enumerate(close.iterrows()):
        week_date = idx.date() if hasattr(idx, 'date') else idx

        # Calculate portfolio value
        portfolio_value = cash
        valid_prices = 0
        for sym, qty in symbols.items():
            price = row.get(sym)
            if price is not None and not (hasattr(price, '__float__') and price != price):  # NaN check
                portfolio_value += float(price) * qty
                valid_prices += 1

        if valid_prices == 0:
            continue

        nav = portfolio_value
        hwm = max(hwm, nav)
        units = 1000.0  # fixed units

        weekly_return = (nav - prev_nav) / prev_nav if prev_nav and prev_nav > 0 else 0.0
        prev_nav = nav

        history.append(WeeklyNAV(
            date=week_date,
            nav=Decimal(str(round(nav, 2))),
            nav_per_unit=Decimal(str(round(nav / units, 4))),
            gross_return_pct=round(weekly_return, 4),
            net_return_pct=round(weekly_return - 0.02 / 52, 4),  # ~2% annual mgmt
            mgmt_fee_accrued=Decimal(str(round(nav * 0.02 / 52, 2))),
            perf_fee_accrued=Decimal("0"),
            high_water_mark=Decimal(str(round(hwm, 2))),
            market_health="green" if weekly_return > 0 else "yellow" if weekly_return > -0.02 else "red",
            momentum="rising" if weekly_return > 0.005 else "falling" if weekly_return < -0.005 else "steady",
            benchmarks={},
            narrative_summary="",
        ))

    print(f"  Got {len(history)} weeks of real NAV data")

    # Get latest prices for broker
    latest_prices = {}
    if not close.empty:
        last_row = close.iloc[-1]
        for sym in symbols:
            price = last_row.get(sym)
            if price is not None and price == price:  # NaN check
                latest_prices[sym] = float(price)

    return history, latest_prices


def fetch_spy_weekly(weeks: int = 52) -> dict:
    """Fetch SPY weekly returns for benchmark comparison."""
    import yfinance as yf

    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks + 1)

    df = yf.download("SPY", start=start_date.isoformat(), end=end_date.isoformat(),
                     interval="1wk", progress=False)
    if df.empty:
        return {}

    close = df["Close"]
    spy_returns = {}
    prev = None
    for idx, val in close.items():
        d = idx.date() if hasattr(idx, 'date') else idx
        price = float(val) if hasattr(val, '__float__') else float(val.iloc[0]) if hasattr(val, 'iloc') else float(val)
        if prev is not None:
            spy_returns[d] = (price - prev) / prev
        prev = price

    return spy_returns


def sync_to_supabase(supabase: SupabaseSync, fund: Fund, broker: _SimBroker,
                     universe: InvestmentUniverse, nav_history: list,
                     health: HealthMonitor):
    """Push all fund state to Supabase for the web dashboard."""
    print("  Syncing fund snapshot...")
    account = broker.get_account()
    positions = broker.get_positions()
    supabase.push_snapshot({
        "date": str(date.today()),
        "nav": float(fund.nav),
        "nav_per_unit": float(fund.nav_per_unit),
        "units_outstanding": float(fund.units_outstanding),
        "high_water_mark": float(fund.high_water_mark),
        "cash": float(account.cash),
        "positions_count": len(positions),
    })

    print("  Syncing positions...")
    total_value = float(account.equity)
    pos_data = []
    for p in positions:
        mv = float(p.market_value)
        pos_data.append({
            "symbol": p.symbol,
            "quantity": float(p.quantity),
            "market_value": mv,
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_pl_pct": p.unrealized_pl_pct,
            "allocation_pct": mv / total_value if total_value > 0 else 0,
        })
    supabase.push_positions(pos_data)

    print("  Syncing engine heartbeat...")
    heartbeat = health.create_heartbeat(
        alpaca_connected=False,
        last_trade=None,
        active_positions=len(positions),
        current_regime="live_analysis",
        next_action="Next analysis tick",
        next_action_at=datetime.now() + timedelta(minutes=5),
    )
    supabase.push_heartbeat({
        "id": "singleton",
        "status": heartbeat.status,
        "alpaca_connected": heartbeat.alpaca_connected,
        "last_trade": heartbeat.last_trade.isoformat() if heartbeat.last_trade else None,
        "active_positions": heartbeat.active_positions,
        "current_regime": heartbeat.current_regime,
        "next_action": heartbeat.next_action,
        "next_action_at": heartbeat.next_action_at.isoformat() if heartbeat.next_action_at else None,
    })

    print("  Syncing weekly NAV history...")
    # Fetch SPY for benchmark
    spy_returns = fetch_spy_weekly()

    for nav in nav_history:
        spy_ret = spy_returns.get(nav.date, 0)
        try:
            supabase._client.table("weekly_nav").upsert({
                "id": str(uuid4()),
                "date": str(nav.date),
                "nav": float(nav.nav),
                "nav_per_unit": float(nav.nav_per_unit),
                "gross_return_pct": nav.gross_return_pct,
                "net_return_pct": nav.net_return_pct,
                "mgmt_fee_accrued": float(nav.mgmt_fee_accrued),
                "perf_fee_accrued": float(nav.perf_fee_accrued),
                "high_water_mark": float(nav.high_water_mark),
                "clarity_score": 0,
                "opportunity_score": 0,
                "capture_rate": 0,
                "market_health": nav.market_health,
                "momentum": nav.momentum,
                "benchmarks": {"SPY": round(spy_ret, 4)},
                "narrative_summary": nav.narrative_summary,
            }, on_conflict="date").execute()
        except Exception as e:
            print(f"    Warning: failed to upsert weekly_nav {nav.date}: {e}")

    print("  Syncing instruments...")
    for inst in universe.instruments:
        try:
            supabase._client.table("instruments").upsert({
                "id": str(uuid4()),
                "symbol": inst.symbol,
                "name": inst.name,
                "asset_class": inst.asset_class,
                "thesis": inst.thesis,
                "proposed_by": inst.proposed_by,
                "added_date": str(inst.added_date),
                "votes_for": inst.votes_for,
            }, on_conflict="symbol").execute()
        except Exception as e:
            print(f"    Warning: failed to upsert instrument {inst.symbol}: {e}")


def main():
    print("=" * 60)
    print("  FUND ENGINE - Live Analysis Server")
    print("=" * 60)

    # ── Load env ──────────────────────────────────────────────
    env_file = Path(__file__).parent.parent / "web" / ".env.local"
    if env_file.exists():
        print(f"\n  Loading env from {env_file}")
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip('"')
                os.environ.setdefault(key.strip(), value)

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    # ── Fetch real market data ─────────────────────────────────
    print("\n  Fetching real market data from Yahoo Finance...")

    nav_history, latest_prices = fetch_real_weekly_history(HOLDINGS)

    if not nav_history:
        print("  FATAL: Could not fetch market data. Check your internet connection.")
        sys.exit(1)
    if not latest_prices:
        # Pre-market / weekend: fetch last daily close
        print("  WARNING: No latest prices from weekly data, fetching daily close...")
        import yfinance as yf
        for sym in HOLDINGS:
            try:
                df = yf.download(sym, period="5d", progress=False)
                if not df.empty:
                    price = df["Close"].iloc[-1]
                    latest_prices[sym] = float(price.iloc[0]) if hasattr(price, 'iloc') else float(price)
            except Exception:
                pass
        if latest_prices:
            print(f"  Got {len(latest_prices)} prices from daily close")
        else:
            print("  WARNING: No stock prices available — engine will use streaming data only (crypto is 24/7)")

    # ── Build fund engine with real prices ─────────────────────
    print("\n  Building fund engine with real prices...")

    # Use first week's prices as avg entry (simulating buying a year ago)
    first_nav = nav_history[0]
    latest_nav = nav_history[-1]

    broker = _SimBroker(cash=STARTING_CASH)
    for symbol, qty in HOLDINGS.items():
        current = latest_prices.get(symbol, 100)
        # Entry price = current price adjusted by portfolio return
        total_return = float(latest_nav.nav) / float(first_nav.nav) if float(first_nav.nav) > 0 else 1.0
        entry_price = current / total_return
        broker.seed_position(symbol, Decimal(str(qty)), Decimal(str(round(entry_price, 2))))
        broker.seed_price(symbol, Decimal(str(round(current, 2))))

    fund = Fund(
        nav=broker.get_account().equity,
        units_outstanding=Decimal("1000"),
        high_water_mark=Decimal(str(float(latest_nav.high_water_mark))),
        inception_date=date(2025, 1, 6),
    )

    universe = InvestmentUniverse(max_size=20)
    for inst in SEED_INSTRUMENTS:
        universe.add(inst)

    journal = EventJournal(journal_dir="/tmp/fund-journals")
    health = HealthMonitor()

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    synthesizer = None
    if openai_key:
        from fund.belief_synthesizer import BeliefSynthesizer
        synthesizer = BeliefSynthesizer(api_key=openai_key, model="gpt-4o-mini")
        print("  Synthesizer:     OpenAI gpt-4o-mini (cached)")
    else:
        from fund.mock_synthesizer import MockSynthesizer
        synthesizer = MockSynthesizer()
        print("  Synthesizer:     Mock (no OPENAI_API_KEY set)")

    account = broker.get_account()
    print(f"\n  Fund NAV:        ${float(fund.nav):,.2f}")
    print(f"  Cash:            ${float(STARTING_CASH):,.2f}")
    print(f"  Positions:       {len(HOLDINGS)} ({', '.join(PORTFOLIO_SYMBOLS)})")
    print(f"  NAV/unit:        ${float(fund.nav_per_unit):,.4f}")
    print(f"  52wk data:       {len(nav_history)} weeks")
    print(f"  1yr return:      {((float(latest_nav.nav) / float(first_nav.nav)) - 1) * 100:+.1f}%")

    # ── Sync to Supabase ──────────────────────────────────────
    supabase = None
    if supabase_url and supabase_key and supabase_key != "your-service-role-key":
        print(f"\n  Syncing to Supabase ({supabase_url})...")
        try:
            supabase = SupabaseSync(SupabaseConfig(url=supabase_url, key=supabase_key))
            sync_to_supabase(supabase, fund, broker, universe, nav_history, health)
            print("  Supabase sync complete!")
        except Exception as e:
            print(f"  Warning: Supabase sync failed: {e}")
    else:
        print("\n  Supabase sync skipped (no SUPABASE_SERVICE_ROLE_KEY set)")

    # ── Read streaming configuration from environment ─────────
    broker_mode = os.environ.get("BROKER_MODE", "paper")
    alpaca_api_key = os.environ.get("ALPACA_API_KEY", "")
    alpaca_secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    alpaca_data_feed = os.environ.get("ALPACA_DATA_FEED", "iex")
    silicondb_url = os.environ.get("SILICONDB_URL", "http://127.0.0.1:8642")
    heartbeat_interval = int(os.environ.get("HEARTBEAT_INTERVAL", "300"))
    thermo_cold = float(os.environ.get("THERMO_COLD", "0.3"))
    thermo_warm = float(os.environ.get("THERMO_WARM", "0.6"))
    thermo_hot = float(os.environ.get("THERMO_HOT", "0.8"))

    portfolio_symbols_env = os.environ.get("PORTFOLIO_SYMBOLS", "")
    reference_symbols_env = os.environ.get("REFERENCE_SYMBOLS", "SPY,QQQ,IWM,DIA")
    macro_proxies_env = os.environ.get("MACRO_PROXIES", "TLT,USO,UUP,UVXY,GLD")
    crypto_symbols_env = os.environ.get("CRYPTO_SYMBOLS", "BTC/USD,ETH/USD,SOL/USD")

    portfolio_syms = [s.strip() for s in portfolio_symbols_env.split(",") if s.strip()] or list(HOLDINGS.keys())
    reference_syms = [s.strip() for s in reference_symbols_env.split(",") if s.strip()]
    macro_syms = [s.strip() for s in macro_proxies_env.split(",") if s.strip()]
    crypto_syms = [s.strip() for s in crypto_symbols_env.split(",") if s.strip()]

    # ── Start embedded SiliconDB (native client with full API) ──
    silicondb_db_path = os.environ.get("SILICONDB_DB_PATH", os.path.expanduser("~/.fund/silicondb"))
    try:
        from silicondb import SiliconDB as SiliconDBNative  # type: ignore[import]

        v1_tenant_id = int(os.environ.get("V1_TENANT_ID", "2"))
        silicondb_client = SiliconDBNative(
            silicondb_db_path,
            enable_beliefs=True,
            enable_theme_discovery=True,
            tenant_id=v1_tenant_id,
        )
        print(f"  SiliconDB:       embedded native client (beliefs=ON, themes=ON, tenant={v1_tenant_id})")
        print(f"  SiliconDB:       path={silicondb_db_path}")
        print(f"  SiliconDB:       thermo_state={hasattr(silicondb_client, 'thermo_state')}, "
              f"epistemic_briefing={hasattr(silicondb_client, 'epistemic_briefing')}, "
              f"subscribe_events={hasattr(silicondb_client, 'subscribe_events')}")
    except Exception as exc:
        silicondb_client = _NullSiliconDB()
        print(f"  SiliconDB:       failed to start embedded ({exc}), using null client")

    # ── Build broker ───────────────────────────────────────────
    live_broker = None
    if alpaca_api_key and alpaca_secret_key:
        try:
            from fund.alpaca_broker import AlpacaBroker
            alpaca_cfg = AlpacaConfig(
                api_key=alpaca_api_key,
                secret_key=alpaca_secret_key,
                paper=(broker_mode != "live"),
            )
            live_broker = AlpacaBroker(alpaca_cfg)
            print(f"  Broker:          AlpacaBroker ({broker_mode} mode)")
        except Exception as exc:
            print(f"  Broker:          AlpacaBroker failed ({exc}), falling back to sim broker")
            live_broker = broker  # _SimBroker already built above
    else:
        live_broker = broker  # _SimBroker
        print(f"  Broker:          SimBroker (no ALPACA_API_KEY set)")

    # ── Load full ticker list from ontology ──────────────────────
    try:
        from fund.ontology import fetch_index_compositions
        sp500, nasdaq100 = fetch_index_compositions()
        all_tracked = sorted(set(sp500 + nasdaq100))
        print(f"  Tracked:         {len(all_tracked)} symbols (S&P 500 + NASDAQ 100)")
    except Exception as exc:
        all_tracked = []
        print(f"  Tracked:         failed to load ({exc}), using portfolio only")

    # ── Build streaming components ─────────────────────────────
    event_queue: queue.Queue = queue.Queue(maxsize=10000)
    price_cache = PriceCache()

    if alpaca_api_key and alpaca_secret_key:
        try:
            stream_cfg = StreamConfig(
                portfolio_symbols=portfolio_syms,
                reference_symbols=reference_syms,
                macro_proxies=macro_syms,
                crypto_symbols=crypto_syms,
                tracked_symbols=all_tracked,
                data_feed=alpaca_data_feed,
            )
            stream_service = AlpacaStreamService(alpaca_cfg, stream_cfg, price_cache, event_queue)
            n_stock = len(stream_cfg.all_stream_symbols)
            n_crypto = len(stream_cfg.all_crypto)
            print(f"  Stream:          AlpacaStreamService ({n_stock} stocks + {n_crypto} crypto, feed={alpaca_data_feed})")
        except Exception as exc:
            print(f"  Stream:          AlpacaStreamService init failed ({exc}), using null stream")
            stream_service = _NullStreamService(event_queue)
    else:
        stream_service = _NullStreamService(event_queue)
        print(f"  Stream:          NullStreamService (no ALPACA_API_KEY set)")

    # ── Build observation, tempo, reactor ─────────────────────
    observation_recorder = ObservationRecorder(price_cache, silicondb_client)
    tempo = Tempo(
        silicondb_client=silicondb_client,
        cold_threshold=thermo_cold,
        warm_threshold=thermo_warm,
        hot_threshold=thermo_hot,
    )
    reactor_config = ReactorConfig(
        portfolio_symbols=portfolio_syms,
        reference_symbols=reference_syms,
    )
    reactor = Reactor(
        silicondb_client=silicondb_client,
        broker=live_broker,
        supabase_sync=supabase,
        price_cache=price_cache,
        tempo=tempo,
        config=reactor_config,
    )

    # ── Load ontology into SiliconDB ─────────────────────────
    if not isinstance(silicondb_client, _NullSiliconDB):
        try:
            from fund.ontology import build_ontology
            triples = build_ontology(use_network=False)
            triple_dicts = [
                {"subject": t.subject, "predicate": t.predicate, "object_value": t.object, "weight": t.weight}
                for t in triples
            ]
            silicondb_client.insert_triples(triple_dicts)
            print(f"  Ontology:        loaded {len(triples)} triples into SiliconDB")
        except Exception as exc:
            print(f"  Ontology:        failed to load ({exc})")

    # ── Build autonomous controller ──────────────────────────
    try:
        from trading_backtest.automation_controller import AutonomousController
        controller = AutonomousController()
        print(f"  Controller:      AutonomousController (regime → strategy → portfolio → trades)")
    except Exception as exc:
        controller = None
        print(f"  Controller:      unavailable ({exc})")

    # ── Build signal tracker ───────────────────────────────────
    from fund.signal_tracker import SignalTracker
    signal_tracker = SignalTracker(
        silicondb_client=silicondb_client,
        portfolio_symbols=portfolio_syms,
    )
    print(f"  Signals:         SignalTracker (watching {len(all_tracked)} symbols)")

    # ── Start live engine (streaming + heartbeat loop) ─────────
    live = LiveEngine(
        symbols=portfolio_syms,
        fund=fund,
        supabase=supabase,
        synthesizer=synthesizer,
        stream_service=stream_service,
        observation_recorder=observation_recorder,
        reactor=reactor,
        tempo=tempo,
        silicondb_client=silicondb_client,
        controller=controller,
        broker=live_broker,
        interval_seconds=heartbeat_interval,
        signal_tracker=signal_tracker,
    )
    live.start()

    # ── Build gRPC servicer ───────────────────────────────────
    thermo = ThermoMetrics()
    benchmarks = BenchmarkEngine()

    class _HealthAdapter:
        def __init__(self, monitor, broker):
            self._monitor = monitor
            self._broker = broker

        def create_heartbeat(self):
            positions = self._broker.get_positions()
            return self._monitor.create_heartbeat(
                alpaca_connected=getattr(live, "_stream", None) is not None and getattr(live._stream, "is_running", False),
                last_trade=None,
                active_positions=len(positions),
                current_regime=getattr(live, "current_regime", "streaming"),
                next_action="Live analysis running",
                next_action_at=datetime.now() + timedelta(minutes=5),
            )

    class _ThermoAdapter:
        def __init__(self, thermo):
            self._thermo = thermo
            self._beliefs = {"AAPL": 0.72, "MSFT": 0.68, "NVDA": 0.75, "GOOG": 0.55, "AMZN": 0.63}

        def clarity_score(self):
            return self._thermo.clarity_score(self._beliefs)

        def opportunity_score(self):
            return self._thermo.opportunity_score(self._beliefs, 0.18)

        def market_health(self):
            return self._thermo.market_health(0.18)

        def momentum(self):
            prev = {s: p - 0.02 for s, p in self._beliefs.items()}
            return self._thermo.momentum(prev, self._beliefs)

        def interpret(self):
            c = self.clarity_score()
            o = self.opportunity_score()
            h = self.market_health()
            m = self.momentum()
            return self._thermo.interpret(c, o, h, m)

    class _BenchmarkAdapter:
        def compare(self):
            return {"SPY": 0.052, "QQQ": 0.071}
        def equal_weight_return(self):
            return 0.065
        def best_daily_pick_return(self):
            return 0.12
        def random_portfolio_median(self):
            return 0.04
        def capture_rate(self):
            return 0.76

    servicer = FundServiceServicer(
        fund=fund,
        members={},
        broker=broker,
        universe=universe,
        journal=journal,
        thermo=_ThermoAdapter(thermo),
        benchmarks=_BenchmarkAdapter(),
        health=_HealthAdapter(health, live_broker),
        belief_synthesizer=synthesizer,
    )
    servicer._nav_history = nav_history

    # ── Start gRPC server ─────────────────────────────────────
    port = int(os.environ.get("GRPC_PORT", "50051"))
    print(f"\n  Starting gRPC server on port {port}...")
    print(f"  Live analysis:   every 5 minutes")
    print(f"  Dashboard:       http://localhost:3000")
    print(f"  Press Ctrl+C to stop\n")
    print("=" * 60)

    journal.log("engine_start", "Fund engine started with real market data")

    try:
        run_server(servicer, port=port)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        live.stop()


if __name__ == "__main__":
    main()
