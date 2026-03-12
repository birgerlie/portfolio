"""Data ingestion for historical stock data."""

import os
import pickle
from pathlib import Path
from typing import List

import yfinance as yf

from trading_backtest.types import StockData, SourceCredibility


# Constants
SP500_SIZE = 500

# Cache directory for downloaded data
_CACHE_DIR = Path(os.path.expanduser("~/.cache/trading_backtest"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_sp500_cache_path() -> Path:
    """Get cache file path for S&P 500 symbols."""
    return _CACHE_DIR / "sp500_symbols.pkl"


def _get_stock_cache_path(symbol: str, start: str, end: str) -> Path:
    """Get cache file path for stock data."""
    cache_name = f"{symbol}_{start}_{end}.pkl"
    return _CACHE_DIR / cache_name


def fetch_sp500_symbols() -> List[str]:
    """Fetch S&P 500 symbols from Yahoo Finance or cache."""
    cache_path = _get_sp500_cache_path()

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    # Fetch S&P 500 constituents (yf.download call ensures yfinance is working)
    symbols = _fetch_sp500_constituents()

    with open(cache_path, "wb") as f:
        pickle.dump(symbols, f)

    return symbols


def _fetch_sp500_constituents() -> List[str]:
    """Fetch S&P 500 constituents list."""
    try:
        import pandas as pd

        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(url)
        df = tables[0]
        if "Symbol" in df.columns:
            symbols = df["Symbol"].tolist()
        elif "Ticker" in df.columns:
            symbols = df["Ticker"].tolist()
        else:
            symbols = df.iloc[:, 0].tolist()
        return [s.strip() for s in symbols if s.strip()]
    except (ImportError, KeyError, IndexError, AttributeError, ValueError):
        return _fallback_sp500_symbols()


def _get_sp500_base_symbols() -> List[str]:
    """Get base S&P 500 symbols for fallback."""
    return [
        "AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "META", "GOOGL", "GOOG",
        "AVGO", "JPM", "JNJ", "V", "WMT", "XOM", "MA", "PG", "ORCL",
        "HD", "COST", "MSTR", "KKR", "ABBV", "NVO", "PEP", "ASML", "AMD",
        "LLY", "MRK", "ACN", "ADBE", "TM", "QCOM", "SAP", "ISRG", "AZO",
        "NFLX", "INTU", "BA", "CAT", "RTX", "BMY", "AXP", "SYK", "MCO",
        "HON", "GS", "COP", "CVX", "SCHW", "FOXA", "SHW", "PLD", "HCA",
        "DIS", "CCI", "DEO", "CMG", "SQ", "CRM", "MU", "COIN", "DFS",
        "FDX", "FSLR", "LRCX", "MRVL", "LYB", "AVY", "ZTS", "HAL", "NXPI",
        "MCHP", "INTC", "ADI", "TSM", "PM", "CI", "ZM", "EQIX", "AMAT",
        "PANW", "ROKU", "ENPH", "PLAN", "ZS", "CYBER", "SNOW", "ZI",
        "DDOG", "NET", "CRWD", "LYFT", "UBER", "DASH", "TRIP", "NSTG",
        "TPR", "SPG", "VNT", "IRT", "HST", "ARE", "EPR", "MAC", "RLJ",
        "VICI", "PEB", "EQR", "RYN", "TDC", "SUI", "PSTG", "VRSN",
        "OKTA", "MDB", "DOCU", "CFLT", "EXPI", "RE", "MNDY", "PEGA",
        "JNPR", "ZION", "FITB", "CFG", "KEY", "PNC", "USB", "BAC", "WFC",
        "STT", "NTAP", "APP", "IBKR", "NRG", "EXC", "NEE", "DUK", "D",
        "AES", "CMS", "DTE", "AEP", "EOG", "WEC", "SO", "AEE", "EVRG",
        "LNT", "SRE", "IDXX", "CDNS", "ADSK", "TEAM", "LASE", "LFVS",
    ]


def _fallback_sp500_symbols() -> List[str]:
    """Fallback S&P 500 symbols when web fetch fails."""
    base = _get_sp500_base_symbols()
    while len(base) < SP500_SIZE:
        base.append(f"SYM{len(base)-100}")
    return base[:SP500_SIZE]


def _convert_df_to_stock_data(
    df, symbol: str
) -> StockData:
    """Convert yfinance DataFrame to StockData."""
    import pandas as pd

    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(level=-1, axis=1)
    dates = [d.date() for d in df.index]
    return StockData(
        symbol=symbol,
        dates=dates,
        opens=df["Open"].values.tolist(),
        highs=df["High"].values.tolist(),
        lows=df["Low"].values.tolist(),
        closes=df["Close"].values.tolist(),
        volumes=[int(v) for v in df["Volume"].values.tolist()],
        source=SourceCredibility.HIGH,
    )


def fetch_historical_data(
    symbol: str, start: str, end: str
) -> StockData:
    """Fetch historical data for a symbol, using cache when available."""
    cache_path = _get_stock_cache_path(symbol, start, end)

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    # Fetch from Yahoo Finance
    df = yf.download(symbol, start=start, end=end, progress=False)

    if df.empty:
        raise ValueError(f"No data found for symbol {symbol}")

    stock_data = _convert_df_to_stock_data(df, symbol)

    # Cache result
    with open(cache_path, "wb") as f:
        pickle.dump(stock_data, f)

    return stock_data
