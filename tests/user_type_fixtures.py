import enum
from dataclasses import dataclass
from typing import Optional


class Color(enum.Enum):
    RED = 1
    GREEN = 2
    BLUE = 3


class Priority(enum.IntEnum):
    LOW = 1
    HIGH = 2


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Box:
    label: str
    size: float
    tag: Optional[Color]
