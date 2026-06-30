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
