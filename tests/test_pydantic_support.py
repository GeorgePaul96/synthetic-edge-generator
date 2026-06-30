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
