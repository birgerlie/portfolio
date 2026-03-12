"""Tests for plain-language thermodynamic metrics."""
import math
import pytest
from fund.thermo_metrics import ThermoMetrics


class TestClarity:
    def test_full_clarity(self):
        metrics = ThermoMetrics()
        beliefs = {"NVDA": 0.99}
        clarity = metrics.clarity_score(beliefs)
        assert clarity > 90

    def test_zero_clarity(self):
        metrics = ThermoMetrics()
        beliefs = {"NVDA": 0.5}
        clarity = metrics.clarity_score(beliefs)
        assert clarity < 10

    def test_mixed_clarity(self):
        metrics = ThermoMetrics()
        beliefs = {"NVDA": 0.88, "AAPL": 0.52, "MSFT": 0.75}
        clarity = metrics.clarity_score(beliefs)
        assert 30 < clarity < 80


class TestOpportunity:
    def test_high_opportunity(self):
        metrics = ThermoMetrics()
        score = metrics.opportunity_score(beliefs={"NVDA": 0.88}, volatility=0.18)
        assert score > 60

    def test_low_opportunity(self):
        metrics = ThermoMetrics()
        score = metrics.opportunity_score(beliefs={"NVDA": 0.52}, volatility=0.45)
        assert score < 30


class TestMarketHealth:
    def test_green(self):
        metrics = ThermoMetrics()
        assert metrics.market_health(volatility=0.15) == "green"

    def test_yellow(self):
        metrics = ThermoMetrics()
        assert metrics.market_health(volatility=0.35) == "yellow"

    def test_red(self):
        metrics = ThermoMetrics()
        assert metrics.market_health(volatility=0.48) == "red"


class TestMomentum:
    def test_rising(self):
        metrics = ThermoMetrics()
        prev = {"NVDA": 0.70, "AAPL": 0.60}
        curr = {"NVDA": 0.80, "AAPL": 0.65}
        assert metrics.momentum(prev, curr) == "rising"

    def test_falling(self):
        metrics = ThermoMetrics()
        prev = {"NVDA": 0.80, "AAPL": 0.65}
        curr = {"NVDA": 0.60, "AAPL": 0.55}
        assert metrics.momentum(prev, curr) == "falling"

    def test_steady(self):
        metrics = ThermoMetrics()
        prev = {"NVDA": 0.75, "AAPL": 0.60}
        curr = {"NVDA": 0.76, "AAPL": 0.59}
        assert metrics.momentum(prev, curr) == "steady"


class TestInterpretation:
    def test_generates_text(self):
        metrics = ThermoMetrics()
        text = metrics.interpret(clarity=82.0, opportunity=71.0, health="green", momentum="rising")
        assert isinstance(text, str)
        assert len(text) > 20
