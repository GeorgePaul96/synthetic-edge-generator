import tempfile
import os

from edge_case_engine.corpus import CorpusManager
from edge_case_engine.recipe import Recipe, materialize
from edge_case_engine.budget import GenerationBudget


def test_envelope_roundtrip_with_integrity():
    with tempfile.TemporaryDirectory() as d:
        cm = CorpusManager(corpus_dir=os.path.join(d, "corpus"),
                           root=os.path.join(d, ".synthedge"))
        r = Recipe(descriptor={"k": "int"}, seed=7, budget=GenerationBudget().to_dict(), lineage=[])
        env = cm.make_envelope(r, materialize(r), artifacts={"exception": None})
        assert env["version"] == 1
        cm.save_interesting(env)
        loaded = cm.load_interesting()
        assert len(loaded) == 1
        assert loaded[0]["recipe"]["seed"] == 7
