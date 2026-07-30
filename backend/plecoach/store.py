"""State access and persistence shared by the API and LiveKit agent."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from abc import ABC, abstractmethod
from typing import Literal, Sequence

from pydantic import BaseModel

from .mastery import (
    build_category_tree,
    summarize_mastery,
    update_mastery,
)
from .schemas import (
    Card,
    DeckMetadata,
    DeckResponse,
    ImportResponse,
    Mastery,
    ParsedPlecoCard,
    PlanningState,
    SessionRecord,
    SessionState,
    TranscriptTurn,
    utc_now,
)

_LEARNER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class StoreError(RuntimeError):
    pass


class DeckNotFoundError(StoreError):
    pass


class SessionNotFoundError(StoreError):
    pass


class CardNotFoundError(StoreError):
    pass


class StoredDeck(BaseModel):
    metadata: DeckMetadata
    cards: list[Card]


def _copy_model(model: BaseModel):
    """Round trip to avoid callers mutating in-memory test state by reference."""

    return type(model).model_validate_json(model.model_dump_json())


def _clean_filename(filename: str) -> str:
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip() or "Pleco deck.xml"
    return basename[:255]


def _deck_name(filename: str) -> str:
    clean = _clean_filename(filename)
    return clean[:-4] if clean.casefold().endswith(".xml") else clean


def _validate_learner_id(learner_id: str) -> None:
    if not _LEARNER_ID_RE.fullmatch(learner_id):
        raise ValueError("learner_id must contain only letters, numbers, '_' or '-'.")


class Store(ABC):
    """Application state boundary; lesson construction lives in SessionPlanner."""

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def _load_deck(self, learner_id: str) -> StoredDeck | None: ...

    @abstractmethod
    async def _save_deck(self, deck: StoredDeck) -> None: ...

    @abstractmethod
    async def _load_planning_state(
        self, learner_id: str
    ) -> PlanningState | None: ...

    @abstractmethod
    async def _save_planning_state(self, state: PlanningState) -> None: ...

    @abstractmethod
    async def _load_session(self, session_id: str) -> SessionRecord | None: ...

    @abstractmethod
    async def _save_session(self, session: SessionRecord) -> None: ...

    @abstractmethod
    async def _save_plan(
        self, planning_state: PlanningState, session: SessionRecord
    ) -> None: ...

    async def import_cards(
        self,
        learner_id: str,
        parsed_cards: Sequence[ParsedPlecoCard],
        source_filename: str,
    ) -> ImportResponse:
        _validate_learner_id(learner_id)
        if not parsed_cards:
            raise ValueError("At least one card is required.")

        now = utc_now()
        existing_deck = await self._load_deck(learner_id)
        existing_by_id = (
            {card.card_id: card for card in existing_deck.cards} if existing_deck else {}
        )
        incoming_by_id = {card.card_id: card for card in parsed_cards}

        merged: list[Card] = []
        for parsed in parsed_cards:
            prior = existing_by_id.get(parsed.card_id)
            merged.append(
                Card(
                    **parsed.model_dump(),
                    active=True,
                    mastery=prior.mastery if prior else Mastery(),
                )
            )
        for card_id, prior in existing_by_id.items():
            if card_id not in incoming_by_id:
                merged.append(prior.model_copy(update={"active": False}))

        active_count = sum(card.active for card in merged)
        inactive_count = len(merged) - active_count
        source_filename = _clean_filename(source_filename)
        metadata = DeckMetadata(
            deck_id=(
                existing_deck.metadata.deck_id
                if existing_deck
                else "deck_" + uuid.uuid4().hex[:16]
            ),
            learner_id=learner_id,
            name=_deck_name(source_filename),
            source_filename=source_filename,
            created_at=existing_deck.metadata.created_at if existing_deck else now,
            updated_at=now,
            card_count=active_count,
            inactive_card_count=inactive_count,
        )
        deck = StoredDeck(metadata=metadata, cards=merged)
        await self._save_deck(deck)

        active_cards = [card for card in merged if card.active]
        active_ids = {card.card_id for card in active_cards}
        planning_state = await self._load_planning_state(learner_id)
        if planning_state is not None:
            planning_state = planning_state.model_copy(
                update={
                    "recent_target_card_ids": [
                        card_id
                        for card_id in planning_state.recent_target_card_ids
                        if card_id in active_ids
                    ],
                    "target_selection_counts": {
                        card_id: count
                        for card_id, count in planning_state.target_selection_counts.items()
                        if card_id in active_ids
                    },
                }
            )
            await self._save_planning_state(planning_state)

        prior_ids = set(existing_by_id)
        incoming_ids = set(incoming_by_id)
        return ImportResponse(
            deck_id=metadata.deck_id,
            learner_id=learner_id,
            name=metadata.name,
            imported_count=len(parsed_cards),
            added_count=len(incoming_ids - prior_ids),
            updated_count=len(incoming_ids & prior_ids),
            inactive_count=inactive_count,
            card_count=active_count,
            category_tree=build_category_tree(active_cards),
            mastery_summary=summarize_mastery(active_cards),
        )

    async def get_deck(self, learner_id: str) -> DeckResponse:
        _validate_learner_id(learner_id)
        deck = await self._load_deck(learner_id)
        if deck is None:
            raise DeckNotFoundError(f"No deck exists for learner '{learner_id}'.")
        active_cards = [card for card in deck.cards if card.active]
        return DeckResponse(
            deck_id=deck.metadata.deck_id,
            learner_id=learner_id,
            name=deck.metadata.name,
            card_count=len(active_cards),
            inactive_card_count=len(deck.cards) - len(active_cards),
            updated_at=deck.metadata.updated_at,
            category_tree=build_category_tree(active_cards),
            mastery_summary=summarize_mastery(active_cards),
            cards=active_cards,
        )

    async def get_planning_state(
        self, learner_id: str
    ) -> PlanningState | None:
        _validate_learner_id(learner_id)
        return await self._load_planning_state(learner_id)

    async def save_plan(
        self, planning_state: PlanningState, session: SessionRecord
    ) -> None:
        _validate_learner_id(planning_state.learner_id)
        if session.learner_id != planning_state.learner_id:
            raise ValueError("Planning state and session must belong to one learner.")
        await self._save_plan(planning_state, session)

    async def get_session(self, session_id: str) -> SessionRecord:
        session = await self._load_session(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{session_id}' was not found.")
        return session

    async def get_session_context(self, session_id: str) -> SessionRecord:
        return await self.get_session(session_id)

    async def set_session_topic(self, session_id: str, topic: str | None) -> SessionRecord:
        session = await self.get_session(session_id)
        cleaned = topic.strip()[:300] if topic and topic.strip() else None
        session = session.model_copy(update={"topic": cleaned, "updated_at": utc_now()})
        await self._save_session(session)
        return session

    async def append_transcript(
        self,
        session_id: str,
        role: Literal["student", "tutor"],
        text: str,
        created_at=None,
    ) -> TranscriptTurn:
        session = await self.get_session(session_id)
        turn = TranscriptTurn(
            turn_id="turn_" + uuid.uuid4().hex[:16],
            role=role,
            text=text.strip(),
            created_at=created_at or utc_now(),
        )
        session = session.model_copy(
            update={
                "state": SessionState.ACTIVE,
                "transcript": [*session.transcript, turn][-200:],
                "updated_at": utc_now(),
            }
        )
        await self._save_session(session)
        return turn

    async def record_assessment(
        self,
        session_id: str,
        card_id: str,
        comprehension: float | None,
        usage: float | None,
        assisted: bool,
        evidence: str,
    ) -> Mastery:
        if comprehension is None and usage is None:
            raise ValueError("An assessment must include comprehension or usage evidence.")
        session = await self.get_session(session_id)
        deck = await self._load_deck(session.learner_id)
        if deck is None:
            raise DeckNotFoundError(f"No deck exists for learner '{session.learner_id}'.")

        cards = list(deck.cards)
        card_index = next((i for i, card in enumerate(cards) if card.card_id == card_id), None)
        if card_index is None:
            raise CardNotFoundError(f"Card '{card_id}' was not found.")
        if not any(target.card_id == card_id for target in session.target_cards):
            raise CardNotFoundError(f"Card '{card_id}' is not a target in this session.")

        current = cards[card_index]
        mastery = update_mastery(
            current.mastery,
            session_id=session_id,
            comprehension=comprehension,
            usage=usage,
            assisted=assisted,
            evidence=evidence,
        )
        cards[card_index] = current.model_copy(update={"mastery": mastery})
        deck = deck.model_copy(
            update={
                "cards": cards,
                "metadata": deck.metadata.model_copy(update={"updated_at": utc_now()}),
            }
        )

        targets = [
            target.model_copy(update={"mastery": mastery, "mastery_state": mastery.state})
            if target.card_id == card_id
            else target
            for target in session.target_cards
        ]
        session = session.model_copy(
            update={
                "state": SessionState.ACTIVE,
                "target_cards": targets,
                "updated_at": utc_now(),
            }
        )
        # Persist the deck first: conversational mastery is the durable outcome.
        await self._save_deck(deck)
        await self._save_session(session)
        return mastery

    async def complete_session(self, session_id: str) -> SessionRecord:
        session = await self.get_session(session_id)
        session = session.model_copy(
            update={"state": SessionState.COMPLETE, "updated_at": utc_now()}
        )
        await self._save_session(session)
        return session


class RedisStore(Store):
    """Production store. Redis is the authoritative application state."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        prefix: str = "plecoach",
        client=None,
        session_ttl_seconds: int | None = None,
    ) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.prefix = prefix
        self.session_ttl_seconds = session_ttl_seconds or int(
            os.getenv("SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60))
        )
        if client is None:
            from redis.asyncio import Redis

            client = Redis.from_url(self.redis_url, decode_responses=True)
        self._redis = client

    def _deck_key(self, learner_id: str) -> str:
        return f"{self.prefix}:learner:{learner_id}:deck"

    def _session_key(self, session_id: str) -> str:
        return f"{self.prefix}:session:{session_id}"

    def _planning_key(self, learner_id: str) -> str:
        return f"{self.prefix}:learner:{learner_id}:planning"

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def close(self) -> None:
        close = getattr(self._redis, "aclose", None)
        if close is not None:
            await close()

    async def _load_deck(self, learner_id: str) -> StoredDeck | None:
        raw = await self._redis.get(self._deck_key(learner_id))
        return StoredDeck.model_validate_json(raw) if raw else None

    async def _save_deck(self, deck: StoredDeck) -> None:
        await self._redis.set(
            self._deck_key(deck.metadata.learner_id), deck.model_dump_json()
        )

    async def _load_planning_state(
        self, learner_id: str
    ) -> PlanningState | None:
        raw = await self._redis.get(self._planning_key(learner_id))
        return PlanningState.model_validate_json(raw) if raw else None

    async def _save_planning_state(self, state: PlanningState) -> None:
        await self._redis.set(
            self._planning_key(state.learner_id),
            state.model_dump_json(),
        )

    async def _load_session(self, session_id: str) -> SessionRecord | None:
        raw = await self._redis.get(self._session_key(session_id))
        return SessionRecord.model_validate_json(raw) if raw else None

    async def _save_session(self, session: SessionRecord) -> None:
        await self._redis.set(
            self._session_key(session.session_id),
            session.model_dump_json(),
            ex=self.session_ttl_seconds,
        )

    async def _save_plan(
        self, planning_state: PlanningState, session: SessionRecord
    ) -> None:
        async with self._redis.pipeline(transaction=True) as transaction:
            transaction.set(
                self._planning_key(planning_state.learner_id),
                planning_state.model_dump_json(),
            )
            transaction.set(
                self._session_key(session.session_id),
                session.model_dump_json(),
                ex=self.session_ttl_seconds,
            )
            await transaction.execute()


class MemoryStore(Store):
    """Explicit test double; never selected by production configuration."""

    def __init__(self) -> None:
        self._decks: dict[str, StoredDeck] = {}
        self._planning_states: dict[str, PlanningState] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def _load_deck(self, learner_id: str) -> StoredDeck | None:
        async with self._lock:
            deck = self._decks.get(learner_id)
            return _copy_model(deck) if deck else None

    async def _save_deck(self, deck: StoredDeck) -> None:
        async with self._lock:
            self._decks[deck.metadata.learner_id] = _copy_model(deck)

    async def _load_planning_state(
        self, learner_id: str
    ) -> PlanningState | None:
        async with self._lock:
            state = self._planning_states.get(learner_id)
            return _copy_model(state) if state else None

    async def _save_planning_state(self, state: PlanningState) -> None:
        async with self._lock:
            self._planning_states[state.learner_id] = _copy_model(state)

    async def _load_session(self, session_id: str) -> SessionRecord | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            return _copy_model(session) if session else None

    async def _save_session(self, session: SessionRecord) -> None:
        async with self._lock:
            self._sessions[session.session_id] = _copy_model(session)

    async def _save_plan(
        self, planning_state: PlanningState, session: SessionRecord
    ) -> None:
        async with self._lock:
            self._planning_states[planning_state.learner_id] = _copy_model(
                planning_state
            )
            self._sessions[session.session_id] = _copy_model(session)
