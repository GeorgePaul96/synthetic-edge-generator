from typing import Optional, List
from pydantic import BaseModel


class Account(BaseModel):
    name: str
    balance: float
    tags: List[int]
    nickname: Optional[str]
