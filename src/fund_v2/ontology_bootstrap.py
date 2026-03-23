"""Bootstrap hook: loads dynamic market ontology into SiliconDB.

Reuses fund/ontology.py (Wikipedia + Yahoo Finance fetch, 50K+ triples).
"""
from fund.ontology import build_ontology


def bootstrap_ontology(app):
    """Called during app.bootstrap() — injects market graph triples."""
    triples = build_ontology(use_network=True)
    app.engine.insert_triples([
        {
            "subject": t.subject,
            "predicate": t.predicate,
            "object": t.object,
            "weight": t.weight,
        }
        for t in triples
    ])
