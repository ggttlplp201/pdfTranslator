from dataclasses import dataclass


@dataclass
class TextUnit:
    text: str
    bbox: tuple[float, float, float, float]
    size: float
    color: int
    bold: bool = False
    italic: bool = False
