"""Shared request, response, and persistence models for Plecoach."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

TUTOR_SPEECH_LIMITS: dict[int, tuple[int, int, int]] = {
    1: (2, 10, 1),
    2: (2, 14, 2),
    3: (2, 18, 2),
    4: (2, 22, 2),
    5: (3, 28, 2),
    6: (3, 34, 3),
    7: (3, 40, 3),
}


def utc_now() -> datetime:
    """Return an aware UTC timestamp.

    A small helper keeps timestamps consistent across the API, Redis store, and
    agent worker.
    """

    return datetime.now(timezone.utc)


class MasteryState(str, Enum):
    UNASSESSED = "unassessed"
    LEARNING = "learning"
    PRACTICING = "practicing"
    FLUENT = "fluent"


class SessionState(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETE = "complete"


class PlecoStats(BaseModel):
    """Review metadata imported from Pleco.

    These values are retained as provenance and a weak planning signal. They
    never initialize or directly determine conversational mastery.
    """

    model_config = ConfigDict(extra="ignore")

    scorefile: str | None = None
    score: int | None = None
    difficulty: int | None = None
    history: str | None = None
    correct: int | None = None
    incorrect: int | None = None
    reviewed: int | None = None
    since_last: int | None = None
    first_reviewed_at: int | None = None
    last_reviewed_at: int | None = None


class AssessmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    comprehension: float | None = Field(default=None, ge=0, le=1)
    usage: float | None = Field(default=None, ge=0, le=1)
    assisted: bool = False
    evidence: str = Field(default="", max_length=1_000)
    created_at: datetime = Field(default_factory=utc_now)


class Mastery(BaseModel):
    """Plecoach's independent, conversation-based mastery state."""

    model_config = ConfigDict(extra="ignore")

    state: MasteryState = MasteryState.UNASSESSED
    comprehension_score: float | None = Field(default=None, ge=0, le=1)
    usage_score: float | None = Field(default=None, ge=0, le=1)
    assessment_count: int = Field(default=0, ge=0)
    independent_successes: int = Field(default=0, ge=0)
    successful_session_ids: list[str] = Field(default_factory=list)
    last_assessed_at: datetime | None = None
    next_review_at: datetime | None = None
    evidence: list[AssessmentEvidence] = Field(default_factory=list)


class ParsedPlecoCard(BaseModel):
    """A normalized card emitted by the XML parser before persistence."""

    model_config = ConfigDict(extra="forbid")

    card_id: str
    simplified: str
    traditional: str
    pinyin: str
    definition: str = Field(default="", max_length=2_000)
    categories: list[str]
    pleco: PlecoStats = Field(default_factory=PlecoStats)
    pleco_created_at: int | None = None
    pleco_modified_at: int | None = None


class Card(ParsedPlecoCard):
    """A persisted card with Plecoach-owned state."""

    active: bool = True
    mastery: Mastery = Field(default_factory=Mastery)


class CategoryNode(BaseModel):
    name: str
    path: str
    card_count: int = Field(ge=0)
    direct_card_count: int = Field(default=0, ge=0)
    children: list["CategoryNode"] = Field(default_factory=list)


class MasterySummary(BaseModel):
    unassessed: int = 0
    learning: int = 0
    practicing: int = 0
    fluent: int = 0


class TutorLanguageProfile(BaseModel):
    """A conservative speaking ceiling inferred from the selected deck scope.

    Target flashcards may sit above the learner's comfortable conversational
    level. The separate support level keeps every other word and grammar pattern
    easier, so the target vocabulary is the only intended challenge.
    """

    model_config = ConfigDict(extra="ignore")

    scope_hsk_level: int = Field(
        default=2,
        ge=1,
        le=7,
        validation_alias=AliasChoices("scope_hsk_level", "target_hsk_level"),
    )
    support_hsk_level: int = Field(default=1, ge=1, le=7)
    confidence: Literal["low", "medium", "high"] = "low"
    labeled_card_count: int = Field(default=0, ge=0)
    scoped_card_count: int = Field(default=0, ge=0)
    support_words: list[str] = Field(default_factory=list, max_length=40)
    max_sentences: int = Field(default=2, ge=1, le=4)
    max_hanzi_per_sentence: int = Field(default=10, ge=6, le=50)
    max_clauses: int = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def validate_coherent_profile(self) -> "TutorLanguageProfile":
        if self.support_hsk_level > self.scope_hsk_level:
            raise ValueError("support_hsk_level cannot exceed scope_hsk_level")
        if self.labeled_card_count > self.scoped_card_count:
            raise ValueError("labeled_card_count cannot exceed scoped_card_count")
        expected_limits = TUTOR_SPEECH_LIMITS[self.support_hsk_level]
        actual_limits = (
            self.max_sentences,
            self.max_hanzi_per_sentence,
            self.max_clauses,
        )
        if actual_limits != expected_limits:
            raise ValueError(
                "speech limits must match the support_hsk_level profile"
            )
        return self


class DeckMetadata(BaseModel):
    deck_id: str
    learner_id: str
    name: str
    source_filename: str
    created_at: datetime
    updated_at: datetime
    card_count: int = Field(ge=0)
    inactive_card_count: int = Field(default=0, ge=0)


class DeckResponse(BaseModel):
    deck_id: str
    learner_id: str
    name: str
    card_count: int
    inactive_card_count: int = 0
    updated_at: datetime
    category_tree: list[CategoryNode]
    mastery_summary: MasterySummary
    cards: list[Card] = Field(default_factory=list)


class PlanningState(BaseModel):
    """Target exposure history kept separate from conversational mastery."""

    learner_id: str
    recent_target_card_ids: list[str] = Field(default_factory=list)
    target_selection_counts: dict[str, int] = Field(default_factory=dict)


class ImportResponse(BaseModel):
    deck_id: str
    learner_id: str
    name: str
    imported_count: int
    added_count: int
    updated_count: int
    inactive_count: int
    card_count: int
    category_tree: list[CategoryNode]
    mastery_summary: MasterySummary


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learner_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    category_paths: list[str] = Field(default_factory=list, max_length=100)
    target_count: int = Field(default=6, ge=1, le=20)


class TargetCard(BaseModel):
    card_id: str
    simplified: str
    traditional: str
    pinyin: str
    categories: list[str]
    definition: str = Field(default="", max_length=2_000)
    pleco: PlecoStats = Field(default_factory=PlecoStats)
    mastery_state: MasteryState
    mastery: Mastery

    @classmethod
    def from_card(cls, card: Card) -> "TargetCard":
        return cls(
            card_id=card.card_id,
            simplified=card.simplified,
            traditional=card.traditional,
            pinyin=card.pinyin,
            categories=card.categories,
            definition=card.definition,
            pleco=card.pleco,
            mastery_state=card.mastery.state,
            mastery=card.mastery,
        )


class TranscriptTurn(BaseModel):
    turn_id: str
    role: Literal["student", "tutor"]
    text: str = Field(min_length=1, max_length=10_000)
    created_at: datetime = Field(default_factory=utc_now)


class SessionRecord(BaseModel):
    session_id: str
    learner_id: str
    room_name: str
    selected_category_paths: list[str]
    language_profile: TutorLanguageProfile = Field(
        default_factory=TutorLanguageProfile
    )
    target_cards: list[TargetCard]
    topic_suggestions: list[str]
    topic: str | None = None
    state: SessionState = SessionState.PLANNED
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def targets(self) -> list[TargetCard]:
        """Compatibility alias used by the voice agent."""

        return self.target_cards


class ConnectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_identity: str | None = Field(
        default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$"
    )
    participant_name: str | None = Field(default=None, min_length=1, max_length=80)
    topic: str | None = Field(default=None, max_length=300)


class LegacyConnectionRequest(ConnectionRequest):
    """Compatibility shape for the early frontend contract."""

    learner_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    session_id: str = Field(min_length=1, max_length=80)


class ConnectionDetails(BaseModel):
    server_url: str
    token: str
    participant_token: str
    room_name: str
    session_id: str
    participant_identity: str


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    card_id: str
    comprehension: float | None = Field(default=None, ge=0, le=1)
    usage: float | None = Field(default=None, ge=0, le=1)
    assisted: bool = False
    evidence: str = Field(default="", max_length=1_000)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    redis: Literal["ok", "unavailable"]
    livekit_configured: bool
