"""Rule-based lesson planning independent of HTTP and storage backends."""

from __future__ import annotations

import asyncio
import uuid
from typing import Protocol, Sequence

from .language_profile import infer_tutor_language_profile
from .mastery import (
    card_matches_categories,
    select_target_cards,
    suggest_topics,
)
from .schemas import (
    DeckResponse,
    PlanningState,
    SessionRecord,
    TargetCard,
    utc_now,
)


class InvalidSelectionError(RuntimeError):
    """Raised when a category selection contains no active flashcards."""


class SessionPlanningStore(Protocol):
    """Persistence operations required to construct and save a lesson plan."""

    async def get_deck(self, learner_id: str) -> DeckResponse: ...

    async def get_planning_state(
        self, learner_id: str
    ) -> PlanningState | None: ...

    async def save_plan(
        self, state: PlanningState, session: SessionRecord
    ) -> None: ...


def _normalize_category_paths(category_paths: Sequence[str]) -> list[str]:
    """Trim, de-duplicate, and discard category paths with no usable value."""

    normalized_paths: list[str] = []
    seen: set[str] = set()
    for path in category_paths:
        normalized = path.strip().strip("/")
        if normalized and normalized not in seen:
            normalized_paths.append(normalized)
            seen.add(normalized)
    return normalized_paths


class SessionPlanner:
    """Construct lesson plans from deck data and target-exposure history."""

    def __init__(self, store: SessionPlanningStore) -> None:
        self._store = store
        self._planning_locks: dict[str, asyncio.Lock] = {}

    async def create_session(
        self,
        learner_id: str,
        category_paths: Sequence[str],
        target_count: int = 6,
    ) -> SessionRecord:
        # Compose runs one API process. A per-learner lock prevents two browser
        # requests in that process from reading and overwriting the same history.
        lock = self._planning_locks.setdefault(learner_id, asyncio.Lock())
        async with lock:
            return await self._create_session(
                learner_id,
                category_paths,
                target_count,
            )

    async def _create_session(
        self,
        learner_id: str,
        category_paths: Sequence[str],
        target_count: int,
    ) -> SessionRecord:
        deck = await self._store.get_deck(learner_id)
        normalized_paths = _normalize_category_paths(category_paths)
        planning_state = await self._store.get_planning_state(learner_id)
        if planning_state is None:
            planning_state = PlanningState(learner_id=learner_id)

        scoped_cards = [
            card
            for card in deck.cards
            if card.active and card_matches_categories(card, normalized_paths)
        ]
        targets = select_target_cards(
            deck.cards,
            normalized_paths,
            target_count,
            recent_target_card_ids=planning_state.recent_target_card_ids,
            target_selection_counts=planning_state.target_selection_counts,
        )
        if not targets:
            raise InvalidSelectionError(
                "The selected categories do not contain any active flashcards."
            )

        session_id = "session_" + uuid.uuid4().hex[:16]
        now = utc_now()
        session = SessionRecord(
            session_id=session_id,
            learner_id=learner_id,
            room_name="plecoach-" + session_id.removeprefix("session_"),
            selected_category_paths=normalized_paths,
            language_profile=infer_tutor_language_profile(
                scoped_cards,
                normalized_paths,
            ),
            target_cards=[TargetCard.from_card(card) for card in targets],
            topic_suggestions=suggest_topics(targets, normalized_paths),
            created_at=now,
            updated_at=now,
        )

        target_ids = [card.card_id for card in targets]
        selection_counts = dict(planning_state.target_selection_counts)
        for card_id in target_ids:
            selection_counts[card_id] = selection_counts.get(card_id, 0) + 1
        planning_state = planning_state.model_copy(
            update={
                "recent_target_card_ids": target_ids,
                "target_selection_counts": selection_counts,
            }
        )

        # History has its own key, so it cannot overwrite concurrent mastery.
        # The store commits history and the session as one persistence operation.
        await self._store.save_plan(planning_state, session)
        return session
