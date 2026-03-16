"""Tests for the expanded market ontology (macro proxies, new observables, benchmarks)."""

import pytest
from fund.ontology import (
    MACRO_PROXIES,
    MACRO_PROXY_SYMBOLS,
    NEW_OBSERVABLES,
    TEMPORAL_PREDICATES,
    REFERENCE_BENCHMARKS,
    build_ontology,
)


@pytest.fixture(scope="module")
def triples():
    return build_ontology(use_network=False)


# ── Constant shape tests ──────────────────────────────────────────────────────

def test_temporal_predicates_constant():
    assert TEMPORAL_PREDICATES == ["leads", "co_moves_with", "inversely_correlated"]


def test_reference_benchmarks_constant():
    assert isinstance(REFERENCE_BENCHMARKS, dict)
    assert REFERENCE_BENCHMARKS["technology"] == "QQQ"
    assert REFERENCE_BENCHMARKS["communication_services"] == "QQQ"
    assert REFERENCE_BENCHMARKS["industrials"] == "DIA"
    # All other sectors map to SPY
    for sector in [
        "consumer_cyclical", "consumer_defensive", "healthcare",
        "financials", "energy", "utilities", "real_estate", "materials",
    ]:
        assert REFERENCE_BENCHMARKS[sector] == "SPY"


def test_new_observables_constant():
    assert NEW_OBSERVABLES == ["vwap", "spread", "trade_intensity", "volume_anomaly"]


# ── MACRO_PROXIES structure tests ─────────────────────────────────────────────

def test_macro_proxies_subjects():
    subjects = [m[0] for m in MACRO_PROXIES]
    assert "TLT" in subjects
    assert "USO" in subjects
    assert "UUP" in subjects
    assert "UVXY" in subjects
    assert "GLD" in subjects
    assert "IWM" in subjects


def test_macro_proxy_symbols_derived():
    assert MACRO_PROXY_SYMBOLS == [m[0] for m in MACRO_PROXIES]


# ── build_ontology() triple tests (use_network=False) ─────────────────────────

def test_macro_proxy_triples_present(triples):
    proxy_for = {(t.subject, t.object) for t in triples if t.predicate == "proxy_for"}
    assert ("TLT", "interest_rates") in proxy_for
    assert ("USO", "oil_prices") in proxy_for
    assert ("UUP", "usd_strength") in proxy_for
    assert ("UVXY", "market_fear") in proxy_for
    assert ("GLD", "gold_prices") in proxy_for
    assert ("IWM", "russell2000") in proxy_for


def test_macro_proxy_proxy_for_weights(triples):
    weights = {(t.subject, t.object): t.weight for t in triples if t.predicate == "proxy_for"}
    assert weights[("TLT", "interest_rates")] == pytest.approx(0.9)
    assert weights[("IWM", "russell2000")] == pytest.approx(1.0)


def test_macro_proxy_symbols_are_instruments(triples):
    instruments = {t.subject for t in triples if t.predicate == "is_a" and t.object == "instrument"}
    for sym in MACRO_PROXY_SYMBOLS:
        assert sym in instruments, f"{sym} not marked as instrument"


def test_macro_proxy_symbols_have_observable_nodes(triples):
    has_obs = {(t.subject, t.predicate) for t in triples}
    for sym in MACRO_PROXY_SYMBOLS:
        for obs in NEW_OBSERVABLES:
            assert (sym, f"has_{obs}") in has_obs, f"Missing has_{obs} for {sym}"


def test_macro_proxy_symbols_have_standard_observables(triples):
    standard = ["price", "volume", "return", "volatility", "market_cap", "momentum", "rsi"]
    has_obs = {(t.subject, t.predicate) for t in triples}
    for sym in MACRO_PROXY_SYMBOLS:
        for obs in standard:
            assert (sym, f"has_{obs}") in has_obs, f"Missing has_{obs} for {sym}"
