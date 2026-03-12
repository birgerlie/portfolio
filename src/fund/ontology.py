"""Market ontology: sectors, indices, supply chains, and competitive relationships.

Dynamically fetches S&P 500 and NASDAQ-100 compositions from Wikipedia,
enriches with sector/industry data from Yahoo Finance, and builds a knowledge
graph for SiliconDB's belief engine to propagate signals through.

Results are cached to disk so we only fetch once per day.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "fund_ontology"
CACHE_TTL = 86400  # 24 hours


@dataclass
class Triple:
    """A directed relationship: subject --predicate--> object with optional weight."""
    subject: str
    predicate: str
    object: str
    weight: float = 1.0


# ── GICS sector mapping (Yahoo Finance sector strings → normalized IDs) ──────

SECTOR_NORMALIZE: Dict[str, str] = {
    "Technology": "technology",
    "Information Technology": "technology",
    "Communication Services": "communication_services",
    "Consumer Cyclical": "consumer_cyclical",
    "Consumer Discretionary": "consumer_cyclical",
    "Consumer Defensive": "consumer_defensive",
    "Consumer Staples": "consumer_defensive",
    "Healthcare": "healthcare",
    "Health Care": "healthcare",
    "Financial Services": "financials",
    "Financials": "financials",
    "Industrials": "industrials",
    "Energy": "energy",
    "Utilities": "utilities",
    "Real Estate": "real_estate",
    "Basic Materials": "materials",
    "Materials": "materials",
}

# ── Known supply chain relationships (curated, high-signal) ──────────────────

# Supply chain edges are intentionally omitted — SiliconDB discovers these
# automatically through add_cooccurrences() and belief propagation from price data.
# Only structural relationships (sector, index, macro) are seeded here.

# ── Known competition pairs (curated) ───────────────────────────────────────

COMPETITORS = [
    ("GOOG", "META", 0.8),     # advertising
    ("AMZN", "MSFT", 0.7),     # cloud
    ("GOOG", "MSFT", 0.5),     # cloud
    ("GOOG", "AMZN", 0.4),     # cloud
    ("AAPL", "GOOG", 0.3),     # mobile OS
    ("AAPL", "MSFT", 0.25),    # hardware/OS
    ("NVDA", "AMD", 0.8),      # GPUs
    ("NVDA", "INTC", 0.4),     # AI accelerators
    ("INTC", "AMD", 0.7),      # CPUs
    ("CRM", "MSFT", 0.6),      # enterprise SaaS
    ("CRM", "ORCL", 0.5),      # CRM
    ("NFLX", "DIS", 0.7),      # streaming
    ("NFLX", "WBD", 0.5),      # streaming
    ("V", "MA", 0.9),           # payments
    ("JPM", "BAC", 0.7),       # banking
    ("JPM", "GS", 0.6),        # investment banking
    ("UNH", "CVS", 0.6),       # health insurance
    ("HD", "LOW", 0.9),        # home improvement
    ("KO", "PEP", 0.9),        # beverages
    ("WMT", "COST", 0.6),      # retail
    ("WMT", "AMZN", 0.5),      # retail/ecommerce
    ("XOM", "CVX", 0.8),       # oil
    ("T", "VZ", 0.8),          # telecom
    ("BA", "LMT", 0.4),        # defense/aerospace
    ("UBER", "LYFT", 0.9),     # rideshare
    ("ABNB", "BKNG", 0.7),     # travel
    ("SNAP", "META", 0.5),     # social
    ("PINS", "META", 0.3),     # social
]

# ── Macro relationships ─────────────────────────────────────────────────────

MACRO = [
    ("interest_rates", "pressures", "technology", 0.6),
    ("interest_rates", "pressures", "real_estate", 0.8),
    ("interest_rates", "pressures", "utilities", 0.5),
    ("interest_rates", "benefits", "financials", 0.5),
    ("oil_prices", "drives", "energy", 0.9),
    ("oil_prices", "pressures", "industrials", 0.3),
    ("china_risk", "pressures", "technology", 0.5),
    ("consumer_spending", "drives", "consumer_cyclical", 0.8),
    ("consumer_spending", "drives", "consumer_defensive", 0.3),
    ("ai_capex", "drives", "technology", 0.7),
    ("ad_spending", "drives", "communication_services", 0.7),
    ("healthcare_policy", "pressures", "healthcare", 0.6),
]

# ── Market structure ─────────────────────────────────────────────────────────

MARKET_STRUCTURE = [
    # Exchanges
    ("NYSE", "is_a", "exchange", 1.0),
    ("NASDAQ", "is_a", "exchange", 1.0),

    # Index hierarchy — what each index represents
    ("SPY", "tracks", "sp500", 1.0),
    ("QQQ", "tracks", "nasdaq100", 1.0),
    ("DIA", "tracks", "dow30", 1.0),
    ("IWM", "tracks", "russell2000", 1.0),
    ("VTI", "tracks", "total_us_market", 1.0),

    # Index relationships — broader to narrower
    ("total_us_market", "contains_index", "sp500", 1.0),
    ("total_us_market", "contains_index", "russell2000", 1.0),
    ("sp500", "overlaps_with", "nasdaq100", 0.85),  # ~85% of QQQ is in SPY
    ("sp500", "overlaps_with", "dow30", 1.0),       # all Dow stocks are in S&P

    # Volatility indices
    ("VIX", "measures_volatility_of", "sp500", 1.0),
    ("VXN", "measures_volatility_of", "nasdaq100", 1.0),

    # Volatility → regime signals
    ("VIX", "signals", "market_fear", 0.9),
    ("market_fear", "pressures", "consumer_cyclical", 0.7),
    ("market_fear", "benefits", "consumer_defensive", 0.4),
    ("market_fear", "pressures", "technology", 0.6),

    # Bond market relationships
    ("10yr_yield", "is_a", "bond_rate", 1.0),
    ("2yr_yield", "is_a", "bond_rate", 1.0),
    ("yield_curve", "derived_from", "10yr_yield", 1.0),
    ("yield_curve", "derived_from", "2yr_yield", 1.0),
    ("yield_curve_inversion", "signals", "recession_risk", 0.7),
    ("recession_risk", "pressures", "consumer_cyclical", 0.8),
    ("recession_risk", "pressures", "financials", 0.6),
    ("recession_risk", "benefits", "consumer_defensive", 0.3),

    # Dollar strength
    ("DXY", "measures", "usd_strength", 1.0),
    ("usd_strength", "pressures", "materials", 0.5),    # commodities priced in USD
    ("usd_strength", "pressures", "energy", 0.4),
    ("usd_strength", "benefits", "consumer_cyclical", 0.2),  # cheaper imports

    # Regime concepts (these get set dynamically by the engine)
    ("bull_regime", "is_a", "market_regime", 1.0),
    ("bear_regime", "is_a", "market_regime", 1.0),
    ("transition_regime", "is_a", "market_regime", 1.0),
    ("consolidation_regime", "is_a", "market_regime", 1.0),
]


def _fetch_sp500_tickers() -> List[str]:
    """Fetch S&P 500 tickers from Wikipedia."""
    import io
    import pandas as pd
    import urllib.request
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode()
    tables = pd.read_html(io.StringIO(html))
    df = tables[0]
    tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
    return sorted(set(tickers))


def _fetch_nasdaq100_tickers() -> List[str]:
    """Fetch NASDAQ-100 tickers from Wikipedia."""
    import io
    import pandas as pd
    import urllib.request
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode()
    tables = pd.read_html(io.StringIO(html))
    for t in tables:
        for col in ["Ticker", "Symbol"]:
            if col in t.columns:
                tickers = t[col].str.replace(".", "-", regex=False).tolist()
                return sorted(set(tickers))
    return []


def _fetch_sector_data(tickers: List[str]) -> Dict[str, Dict[str, str]]:
    """Fetch sector and industry for each ticker from Yahoo Finance.

    Returns {ticker: {"sector": ..., "industry": ...}}.
    """
    import yfinance as yf

    result: Dict[str, Dict[str, str]] = {}
    # Batch fetch using yf.Tickers
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        tickers_str = " ".join(batch)
        try:
            data = yf.Tickers(tickers_str)
            for symbol in batch:
                try:
                    info = data.tickers[symbol].info
                    sector = info.get("sector", "")
                    industry = info.get("industry", "")
                    if sector:
                        result[symbol] = {"sector": sector, "industry": industry}
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Failed to fetch batch %d: %s", i, e)
        # Be polite to Yahoo
        time.sleep(0.5)

    return result


def _load_cache(name: str) -> Optional[dict]:
    """Load cached data if fresh enough."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if time.time() - data.get("_ts", 0) < CACHE_TTL:
            return data
    return None


def _save_cache(name: str, data: dict) -> None:
    """Save data to cache with timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data["_ts"] = time.time()
    (CACHE_DIR / f"{name}.json").write_text(json.dumps(data))


def fetch_index_compositions() -> Tuple[List[str], List[str]]:
    """Fetch S&P 500 and NASDAQ-100 compositions (cached daily)."""
    cached = _load_cache("index_compositions")
    if cached:
        return cached["sp500"], cached["nasdaq100"]

    logger.info("Fetching index compositions from Wikipedia...")
    sp500 = _fetch_sp500_tickers()
    nasdaq100 = _fetch_nasdaq100_tickers()
    _save_cache("index_compositions", {"sp500": sp500, "nasdaq100": nasdaq100})
    logger.info("Fetched %d S&P 500 and %d NASDAQ-100 tickers", len(sp500), len(nasdaq100))
    return sp500, nasdaq100


def fetch_all_sector_data(tickers: List[str]) -> Dict[str, Dict[str, str]]:
    """Fetch sector/industry data for all tickers (cached daily)."""
    cached = _load_cache("sector_data")
    if cached:
        sectors = {k: v for k, v in cached.items() if k != "_ts"}
        # Check if we have most tickers
        missing = [t for t in tickers if t not in sectors]
        if len(missing) < 20:
            return sectors

    logger.info("Fetching sector data for %d tickers from Yahoo Finance...", len(tickers))
    sectors = _fetch_sector_data(tickers)
    _save_cache("sector_data", sectors)
    logger.info("Got sector data for %d tickers", len(sectors))
    return sectors


def build_ontology(use_network: bool = True) -> List[Triple]:
    """Build the full market ontology as a list of triples.

    If use_network=True, fetches real S&P 500 / NASDAQ-100 compositions
    and sector data from Yahoo Finance (cached for 24h).
    If False, uses only the curated supply chain / competition data.
    """
    triples: List[Triple] = []

    if use_network:
        sp500, nasdaq100 = fetch_index_compositions()
        all_tickers = sorted(set(sp500 + nasdaq100))
        sectors = fetch_all_sector_data(all_tickers)
    else:
        sp500, nasdaq100 = [], []
        all_tickers = []
        sectors = {}

    # ── Sector membership ────────────────────────────────────────────────
    for symbol, info in sectors.items():
        raw_sector = info.get("sector", "")
        sector_id = SECTOR_NORMALIZE.get(raw_sector, raw_sector.lower().replace(" ", "_"))
        if sector_id:
            triples.append(Triple(symbol, "in_sector", sector_id, 1.0))
            triples.append(Triple(sector_id, "contains_instrument", symbol, 1.0))

        industry = info.get("industry", "")
        if industry:
            industry_id = industry.lower().replace(" ", "_").replace("-", "_").replace("—", "_")
            triples.append(Triple(symbol, "in_industry", industry_id, 1.0))
            triples.append(Triple(industry_id, "contains_instrument", symbol, 1.0))
            # Industry belongs to sector
            if sector_id:
                triples.append(Triple(industry_id, "part_of", sector_id, 1.0))

    # ── Ticker observable properties ──────────────────────────────────────
    # Each ticker has observable attributes that SiliconDB can track beliefs on
    OBSERVABLES = ["price", "volume", "return", "volatility", "market_cap", "momentum", "rsi"]
    for symbol in all_tickers:
        triples.append(Triple(symbol, "is_a", "instrument", 1.0))
        for obs in OBSERVABLES:
            node_id = f"{symbol}:{obs}"
            triples.append(Triple(symbol, f"has_{obs}", node_id, 1.0))
            triples.append(Triple(node_id, "property_of", symbol, 1.0))
            triples.append(Triple(node_id, "is_a", obs, 1.0))

    # ── Index membership ─────────────────────────────────────────────────
    # Equal weight since we don't have exact weights for all 500+ stocks
    if sp500:
        w = 1.0 / len(sp500)
        for symbol in sp500:
            triples.append(Triple("SPY", "contains", symbol, w))
            triples.append(Triple(symbol, "member_of", "SPY", w))

    if nasdaq100:
        w = 1.0 / len(nasdaq100)
        for symbol in nasdaq100:
            triples.append(Triple("QQQ", "contains", symbol, w))
            triples.append(Triple(symbol, "member_of", "QQQ", w))

    # ── Competition (curated, bidirectional) ─────────────────────────────
    for a, b, weight in COMPETITORS:
        triples.append(Triple(a, "competes_with", b, weight))
        triples.append(Triple(b, "competes_with", a, weight))

    # ── Same-industry competition (auto-generated, weak signal) ──────────
    # Group tickers by industry, add weak competition edges
    industry_groups: Dict[str, List[str]] = {}
    for symbol, info in sectors.items():
        industry = info.get("industry", "")
        if industry:
            industry_groups.setdefault(industry, []).append(symbol)

    for industry, members in industry_groups.items():
        if 2 <= len(members) <= 20:  # skip too-large groups
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    # Weak competition signal (same industry)
                    triples.append(Triple(a, "competes_with", b, 0.2))
                    triples.append(Triple(b, "competes_with", a, 0.2))

    # ── Macro relationships ──────────────────────────────────────────────
    for subj, pred, obj, weight in MACRO:
        triples.append(Triple(subj, pred, obj, weight))

    # ── Market structure ─────────────────────────────────────────────────
    for subj, pred, obj, weight in MARKET_STRUCTURE:
        triples.append(Triple(subj, pred, obj, weight))

    logger.info(
        "Ontology built: %d triples, %d tickers, %d sectors",
        len(triples), len(all_tickers), len(set(SECTOR_NORMALIZE.values())),
    )
    return triples


# ── Path finding & explanation ───────────────────────────────────────────────

def get_propagation_paths(symbol: str, triples: List[Triple], max_depth: int = 3) -> List[List[Tuple[str, str, float]]]:
    """Find all propagation paths from a symbol through the ontology."""
    adj: Dict[str, List[Tuple[str, str, float]]] = {}
    for t in triples:
        adj.setdefault(t.subject, []).append((t.object, t.predicate, t.weight))

    paths: List[List[Tuple[str, str, float]]] = []
    visited = {symbol}

    def dfs(node: str, path: List[Tuple[str, str, float]], depth: int):
        if depth >= max_depth:
            return
        for next_node, pred, weight in adj.get(node, []):
            if next_node not in visited:
                visited.add(next_node)
                new_path = path + [(next_node, pred, weight)]
                paths.append(new_path)
                dfs(next_node, new_path, depth + 1)
                visited.discard(next_node)

    dfs(symbol, [], 0)
    return paths


def explain_signal_path(from_symbol: str, to_symbol: str, triples: List[Triple]) -> Optional[str]:
    """Explain how a signal propagates from one symbol to another."""
    paths = get_propagation_paths(from_symbol, triples)

    for path in paths:
        if path[-1][0] == to_symbol:
            steps = [from_symbol]
            cumulative_weight = 1.0
            for node, pred, weight in path:
                steps.append(f"--{pred}({weight:.0%})--> {node}")
                cumulative_weight *= weight
            return f"{' '.join(steps)} (signal strength: {cumulative_weight:.0%})"

    return None


# ── Convenience ──────────────────────────────────────────────────────────────

def symbols_in_sector(sector_id: str, triples: List[Triple]) -> List[Tuple[str, float]]:
    """Get all instruments in a sector with their weights."""
    return [
        (t.object, t.weight) for t in triples
        if t.subject == sector_id and t.predicate == "contains_instrument"
    ]


def indices_for_symbol(symbol: str, triples: List[Triple]) -> List[Tuple[str, float]]:
    """Get all indices a symbol belongs to with its weight in each."""
    return [
        (t.object, t.weight) for t in triples
        if t.subject == symbol and t.predicate == "member_of"
    ]


def suppliers_for(symbol: str, triples: List[Triple]) -> List[Tuple[str, float]]:
    """Get all suppliers for a symbol."""
    return [
        (t.subject, t.weight) for t in triples
        if t.object == symbol and t.predicate == "supplies"
    ]


def competitors_for(symbol: str, triples: List[Triple]) -> List[Tuple[str, float]]:
    """Get all competitors for a symbol."""
    return [
        (t.object, t.weight) for t in triples
        if t.subject == symbol and t.predicate == "competes_with"
    ]


# ── Trade / position triples (dynamic, added at runtime) ────────────────────

def record_trade(action: str, symbol: str, allocation: float, reason: str = "") -> List[Triple]:
    """Generate triples for a trade event.

    action: "BUY" or "SELL"
    Returns triples to add to the live ontology.
    """
    triples = []
    pred = "bought" if action == "BUY" else "sold"

    # Fund → instrument relationship
    triples.append(Triple("fund", pred, symbol, allocation))

    # If buying, instrument is now a position
    if action == "BUY":
        triples.append(Triple(symbol, "position_in", "portfolio", allocation))
    else:
        # Selling reduces/removes position (weight 0 signals removal)
        triples.append(Triple(symbol, "exited_from", "portfolio", allocation))

    return triples


def portfolio_triples(positions: Dict[str, float]) -> List[Triple]:
    """Generate triples for current portfolio state.

    positions: {symbol: allocation_weight} e.g. {"NVDA": 0.20, "AAPL": 0.15}
    """
    triples = []
    for symbol, weight in positions.items():
        triples.append(Triple("portfolio", "holds", symbol, weight))
        triples.append(Triple(symbol, "position_in", "portfolio", weight))
    return triples
