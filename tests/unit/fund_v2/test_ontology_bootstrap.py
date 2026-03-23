"""Ontology bootstrap — loads market graph from existing ontology.py."""
from unittest.mock import MagicMock, patch


def test_bootstrap_calls_insert_triples(app):
    from fund_v2.ontology_bootstrap import bootstrap_ontology

    mock_triples = [
        MagicMock(subject="AAPL", predicate="in_sector", object="technology", weight=1.0),
        MagicMock(subject="NVDA", predicate="competes_with", object="AMD", weight=0.8),
    ]
    app._engine.insert_triples = MagicMock()

    with patch("fund_v2.ontology_bootstrap.build_ontology", return_value=mock_triples):
        bootstrap_ontology(app)

    app._engine.insert_triples.assert_called_once()
    triples_arg = app._engine.insert_triples.call_args[0][0]
    assert len(triples_arg) == 2
    assert triples_arg[0]["subject"] == "AAPL"
