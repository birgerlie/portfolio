"""Shared fixtures for fund_v2 unit tests."""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
# Ensure silicondb is importable
sys.path.insert(0, str(_ROOT / "lib" / "silicondb" / "python"))
# Ensure fund_v2 package is importable
sys.path.insert(0, str(_ROOT / "src"))

from silicondb.engine.mock import MockEngine
from silicondb.orm import App


@pytest.fixture
def mock_engine():
    """In-memory SiliconDB engine — no native library needed."""
    return MockEngine()


@pytest.fixture
def app(mock_engine):
    """ORM App wired to MockEngine."""
    return App(mock_engine, internal_db_url="sqlite:///:memory:")
