from __future__ import annotations

import asyncio

import pytest

from plecoach.schemas import (
    Card,
    DeckResponse,
    MasterySummary,
    ParsedPlecoCard,
    PlanningState,
    PlecoStats,
    SessionRecord,
    utc_now,
)
from plecoach.session_planner import InvalidSelectionError, SessionPlanner
from plecoach.store import MemoryStore


class FakePlanningStore:
    """Minimal structural implementation of SessionPlanningStore for unit tests."""

    def __init__(
        self,
        deck: DeckResponse,
        planning_state: PlanningState | None = None,
    ) -> None:
        self.deck = deck
        self.planning_state = planning_state
        self.saved_planning_states: list[PlanningState] = []
        self.saved_sessions: list[SessionRecord] = []

    async def get_deck(self, learner_id: str) -> DeckResponse:
        assert learner_id == self.deck.learner_id
        return self.deck

    async def get_planning_state(
        self, learner_id: str
    ) -> PlanningState | None:
        assert learner_id == self.deck.learner_id
        return self.planning_state

    async def save_plan(
        self, state: PlanningState, session: SessionRecord
    ) -> None:
        self.saved_planning_states.append(state)
        self.saved_sessions.append(session)


def deck_response(*cards: Card) -> DeckResponse:
    return DeckResponse(
        deck_id="deck-test",
        learner_id="learner",
        name="Test deck",
        card_count=len(cards),
        updated_at=utc_now(),
        category_tree=[],
        mastery_summary=MasterySummary(unassessed=len(cards)),
        cards=list(cards),
    )


def equal_priority_cards(count: int) -> list[ParsedPlecoCard]:
    return [
        ParsedPlecoCard(
            card_id=f"card-{index}",
            simplified=f"词{index}",
            traditional=f"詞{index}",
            pinyin=f"ci2-{index}",
            categories=["Course/Lesson"],
        )
        for index in range(count)
    ]


def varied_priority_cards(count: int) -> list[ParsedPlecoCard]:
    return [
        ParsedPlecoCard(
            card_id=f"varied-card-{index}",
            simplified=f"词{index}",
            traditional=f"詞{index}",
            pinyin=f"ci2-{index}",
            categories=["Course/Lesson"],
            pleco=PlecoStats(
                reviewed=10,
                correct=10 - (index % 11),
                incorrect=index % 11,
                score=(index * 7_919) % 30_001,
            ),
        )
        for index in range(count)
    ]


def test_normalizes_categories_and_persists_plan_through_minimal_contract() -> None:
    async def scenario() -> None:
        card = Card(
            card_id="card-one",
            simplified="地图",
            traditional="地圖",
            pinyin="di4tu2",
            categories=["Course/Lesson"],
        )
        store = FakePlanningStore(deck_response(card))
        planner = SessionPlanner(store)

        session = await planner.create_session(
            "learner",
            [" /Course/Lesson/ ", "Course/Lesson", "//"],
            target_count=1,
        )

        assert session.selected_category_paths == ["Course/Lesson"]
        assert [target.card_id for target in session.target_cards] == ["card-one"]
        assert store.saved_sessions == [session]
        assert len(store.saved_planning_states) == 1
        assert store.saved_planning_states[0].recent_target_card_ids == ["card-one"]
        assert store.saved_planning_states[0].target_selection_counts == {
            "card-one": 1
        }

    asyncio.run(scenario())


def test_invalid_selection_does_not_write_planning_state_or_session() -> None:
    async def scenario() -> None:
        card = Card(
            card_id="card-one",
            simplified="地图",
            traditional="地圖",
            pinyin="di4tu2",
            categories=["Course/Lesson"],
        )
        store = FakePlanningStore(deck_response(card))
        planner = SessionPlanner(store)

        with pytest.raises(
            InvalidSelectionError,
            match="selected categories do not contain any active flashcards",
        ):
            await planner.create_session("learner", ["Missing"], target_count=1)

        assert store.saved_planning_states == []
        assert store.saved_sessions == []

    asyncio.run(scenario())


def test_parent_category_selects_descendants_without_duplicate_targets() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        cards = [
            ParsedPlecoCard(
                card_id="lost",
                simplified="迷路",
                traditional="迷路",
                pinyin="mi2lu4",
                categories=["Travel/Directions"],
            ),
            ParsedPlecoCard(
                card_id="map",
                simplified="地图",
                traditional="地圖",
                pinyin="di4tu2",
                categories=["Travel/Directions", "Course/Week 1"],
            ),
        ]
        await store.import_cards("learner", cards, "deck.xml")

        session = await planner.create_session("learner", ["Travel"], target_count=10)

        assert len(session.target_cards) == 2
        assert len({card.card_id for card in session.target_cards}) == 2

    asyncio.run(scenario())


def test_concurrent_plans_rotate_equally_eligible_focus_cards() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        await store.import_cards("learner", equal_priority_cards(12), "deck.xml")

        first, second = await asyncio.gather(
            planner.create_session(
                "learner", ["Course/Lesson"], target_count=6
            ),
            planner.create_session(
                "learner", ["Course/Lesson"], target_count=6
            ),
        )

        first_ids = {card.card_id for card in first.target_cards}
        second_ids = {card.card_id for card in second.target_cards}
        assert first.session_id != second.session_id
        assert first_ids.isdisjoint(second_ids)

    asyncio.run(scenario())


def test_reimport_preserves_focus_card_rotation_history() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        cards = equal_priority_cards(12)
        await store.import_cards("learner", cards, "deck.xml")
        first = await planner.create_session(
            "learner", ["Course/Lesson"], target_count=6
        )

        await store.import_cards("learner", cards, "deck.xml")
        second = await planner.create_session(
            "learner", ["Course/Lesson"], target_count=6
        )

        assert {
            card.card_id for card in first.target_cards
        }.isdisjoint(card.card_id for card in second.target_cards)

    asyncio.run(scenario())


def test_focus_cards_keep_rotating_across_many_plans() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        await store.import_cards("learner", varied_priority_cards(38), "deck.xml")

        previous_ids: set[str] | None = None
        for _ in range(12):
            session = await planner.create_session(
                "learner", ["Course/Lesson"], target_count=6
            )
            target_ids = {card.card_id for card in session.target_cards}
            if previous_ids is not None:
                assert previous_ids.isdisjoint(target_ids)
            previous_ids = target_ids

    asyncio.run(scenario())
