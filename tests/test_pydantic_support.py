import pytest

pydantic = pytest.importorskip("pydantic")   # whole module skips if Pydantic is absent

from edge_case_engine._pydantic import is_model, is_model_type, BaseModel
from tests.pydantic_fixtures import Account


def test_shim_detects_models():
    assert BaseModel is not None
    assert is_model_type(Account) is True
    inst = Account.model_construct(name="a", balance=1.0, tags=[], nickname=None)
    assert is_model(inst) is True
    assert is_model_type(int) is False
    assert is_model(5) is False


import math
from edge_case_engine.codec import encode, decode, values_equal


def test_model_codec_roundtrip_including_nan_and_adversarial_field():
    acct = Account.model_construct(name=None, balance=float("nan"), tags=[1, 2], nickname="n")
    restored = decode(encode(acct))
    assert values_equal(restored, acct)
    assert restored.name is None
    assert math.isnan(restored.balance)


def test_values_equal_model_distinguishes_fields():
    a = Account.model_construct(name="a", balance=1.0, tags=[], nickname=None)
    b = Account.model_construct(name="a", balance=1.0, tags=[], nickname=None)
    c = Account.model_construct(name="a", balance=2.0, tags=[], nickname=None)
    assert values_equal(a, b) is True
    assert values_equal(a, c) is False


import random
from edge_case_engine.budget import GenerationBudget
from type_handlers.pydantic_handler import PydanticHandler
from type_handlers.scalars import IntegerHandler, FloatHandler, StringHandler
from type_handlers.list_handler import ListHandler
from type_handlers.optional_handler import OptionalHandler


def test_pydantic_handler_constructs_instance_deterministically():
    fields = {"name": StringHandler(), "balance": FloatHandler(),
              "tags": ListHandler(IntegerHandler()), "nickname": OptionalHandler(StringHandler())}
    h = PydanticHandler(Account, fields)
    v1 = h.generate(random.Random(2), GenerationBudget())
    v2 = h.generate(random.Random(2), GenerationBudget())
    assert is_model(v1) and values_equal(v1, v2)
    assert h.type_sig() == "pydantic[Account]"
    assert h.descriptor()["k"] == "pydantic" and "balance" in h.descriptor()["fields"]


from type_handlers.resolver import TypeResolver


def test_resolver_maps_model_and_roundtrips_descriptor():
    h = TypeResolver.resolve(Account)
    assert isinstance(h, PydanticHandler)
    assert set(h.fields.keys()) == {"name", "balance", "tags", "nickname"}
    assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()
    r = TypeResolver()
    r.resolve_tracked(Account)
    assert r.fallback_rate() == 0.0


from edge_case_engine.recipe import Recipe, materialize


def test_account_recipe_replays_over_many_seeds():
    h = TypeResolver.resolve(Account)
    budget = GenerationBudget().to_dict()
    for seed in range(100):
        rng = random.Random(seed)
        recipe = Recipe(h.descriptor(), rng.getrandbits(64), budget, [])
        a = materialize(recipe)
        b = materialize(recipe)
        assert values_equal(a, b)
        assert values_equal(decode(encode(a)), a)


def test_run_fuzzer_mode_a_model_param(tmp_path):
    from synthedge.cli import run_fuzzer
    target = tmp_path / "ma.py"
    target.write_text(
        "from pydantic import BaseModel\n"
        "from edge_case_engine.contracts import fuzz_contract\n"
        "class A(BaseModel):\n"
        "    x: int\n"
        "    y: float\n"
        "@fuzz_contract(allowed_exceptions=(Exception,))\n"
        "def use(a: A):\n"
        "    return a.x\n"
    )
    summary = run_fuzzer(str(target), iterations=30, seed=1)
    assert "use" in summary and summary["use"]["iterations"] == 30


def test_run_fuzzer_mode_b_model_validate(tmp_path):
    from synthedge.cli import run_fuzzer
    target = tmp_path / "mb.py"
    target.write_text(
        "from pydantic import BaseModel, ValidationError\n"
        "from edge_case_engine.contracts import fuzz_contract\n"
        "class A(BaseModel):\n"
        "    x: int\n"
        "@fuzz_contract(allowed_exceptions=(ValidationError, TypeError))\n"
        "def check(data: dict) -> A:\n"
        "    return A.model_validate(data)\n"
    )
    summary = run_fuzzer(str(target), iterations=30, seed=1)
    assert "check" in summary and summary["check"]["iterations"] == 30
