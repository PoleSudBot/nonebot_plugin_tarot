from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .data_source import FormationSpec


@dataclass(frozen=True)
class ParsedTarotCommand:
    command: str
    raw_arg: str | None
    formation_query: str | None
    question: str | None
    is_ai: bool


@dataclass(frozen=True)
class BonusCommand:
    target_user_id: str
    count: int


TarotAIFailureCategory = Literal["user_input", "upstream", "filtered", "internal"]


@dataclass(frozen=True)
class TarotAIRequestContext:
    question: str
    formation: "FormationSpec"
    user_id: str
    platform: str
    is_superuser: bool
    cost_gold: int


@dataclass(frozen=True)
class TarotCardDraw:
    index: int
    label: str
    position_name: str
    card_name: str
    orientation: Literal["正位", "逆位"]
    meaning: str
    image_bytes: bytes
    thumbnail_bytes: bytes

    @property
    def display_title(self) -> str:
        return f"{self.label}「{self.position_name}」" if self.position_name else self.label

    @property
    def card_title(self) -> str:
        return f"{self.card_name}{self.orientation}"


@dataclass(frozen=True)
class TarotReading:
    formation_name: str
    formation_prompt: str
    theme: str
    cards: tuple[TarotCardDraw, ...]
