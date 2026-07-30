from __future__ import annotations

import asyncio
from typing import Any

import pytest

from plecoach.pleco_parser import parse_pleco_xml
from plecoach.schemas import MasteryState, PlanningState, SessionRecord
from plecoach.session_planner import SessionPlanner
from plecoach.store import DeckNotFoundError, MemoryStore, RedisStore


XML_V1 = b"""<plecoflash formatversion="2"><cards>
  <card modified="1"><entry>
    <headword charset="sc">&#36855;&#36335;</headword>
    <headword charset="tc">&#36855;&#36335;</headword>
    <pron type="hypy">mi2lu4</pron>
  </entry><catassign category="Travel/Directions"/>
  <scoreinfo score="99999" correct="100" incorrect="0" reviewed="100"/></card>
  <card modified="1"><entry>
    <headword charset="sc">&#22320;&#22270;</headword>
    <headword charset="tc">&#22320;&#22294;</headword>
    <pron type="hypy">di4tu2</pron>
    <defn>a map used for finding places</defn>
  </entry><catassign category="Travel/Directions"/>
  <catassign category="Course/Week 1"/></card>
</cards></plecoflash>"""

XML_V2 = b"""<plecoflash formatversion="2"><cards>
  <card modified="2"><entry>
    <headword charset="sc">&#36855;&#36335;</headword>
    <headword charset="tc">&#36855;&#36335;</headword>
    <pron type="hypy">mi2lu4</pron>
  </entry><catassign category="Travel/Updated"/></card>
</cards></plecoflash>"""


class RecordingPipeline:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.executed = False

    async def __aenter__(self) -> "RecordingPipeline":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    def set(
        self, key: str, value: str, *, ex: int | None = None
    ) -> "RecordingPipeline":
        self.set_calls.append((key, value, ex))
        return self

    async def execute(self) -> list[object]:
        self.executed = True
        return []


class RecordingRedis:
    def __init__(self) -> None:
        self.transaction: bool | None = None
        self.pipeline_instance = RecordingPipeline()
        self.delete_calls: list[tuple[str, ...]] = []

    def pipeline(self, *, transaction: bool) -> RecordingPipeline:
        self.transaction = transaction
        return self.pipeline_instance

    async def delete(self, *keys: str) -> int:
        self.delete_calls.append(keys)
        return len(keys)


def test_redis_store_commits_planning_state_and_session_in_one_transaction() -> None:
    async def scenario() -> None:
        redis = RecordingRedis()
        store = RedisStore(
            client=redis,
            session_ttl_seconds=123,
        )
        planning_state = PlanningState(learner_id="learner")
        session = SessionRecord(
            session_id="session-test",
            learner_id="learner",
            room_name="room-test",
            selected_category_paths=[],
            target_cards=[],
            topic_suggestions=[],
        )

        await store.save_plan(planning_state, session)

        assert redis.transaction is True
        assert redis.pipeline_instance.executed is True
        assert [
            (key, ttl)
            for key, _, ttl in redis.pipeline_instance.set_calls
        ] == [
            ("plecoach:learner:learner:planning", None),
            ("plecoach:session:session-test", 123),
        ]

    asyncio.run(scenario())


def test_redis_store_deletes_only_the_learner_persistent_keys() -> None:
    async def scenario() -> None:
        redis = RecordingRedis()
        store = RedisStore(client=redis)

        await store.delete_learner_data("learner")

        assert redis.delete_calls == [
            (
                "plecoach:learner:learner:deck",
                "plecoach:learner:learner:planning",
            )
        ]

    asyncio.run(scenario())


def test_delete_learner_data_removes_deck_and_planning_but_keeps_ttl_session() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        await store.import_cards("learner-1", parse_pleco_xml(XML_V1), "first.xml")
        await store.import_cards("learner-2", parse_pleco_xml(XML_V1), "second.xml")
        session = await planner.create_session(
            "learner-1", ["Travel/Directions"], target_count=2
        )

        await store.delete_learner_data("learner-1")

        with pytest.raises(DeckNotFoundError):
            await store.get_deck("learner-1")
        assert await store.get_planning_state("learner-1") is None
        assert (await store.get_session(session.session_id)).learner_id == "learner-1"
        assert (await store.get_deck("learner-2")).card_count == 2

        # Retrying a reset is safe even when the learner no longer has data.
        await store.delete_learner_data("learner-1")

    asyncio.run(scenario())


def test_import_session_assessment_and_reimport_preserve_plecoach_mastery() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        first = await store.import_cards("learner-1", parse_pleco_xml(XML_V1), "first.xml")
        assert first.added_count == 2
        assert first.mastery_summary.unassessed == 2

        deck = await store.get_deck("learner-1")
        assert all(card.mastery.state == MasteryState.UNASSESSED for card in deck.cards)
        travel = next(node for node in deck.category_tree if node.path == "Travel")
        assert travel.path == "Travel"
        assert travel.card_count == 2
        assert travel.children[0].path == "Travel/Directions"

        session = await planner.create_session(
            "learner-1", ["Travel/Directions"], target_count=2
        )
        map_target = next(
            card for card in session.target_cards if card.simplified == "地图"
        )
        assert map_target.definition == "a map used for finding places"
        assessed_card_id = next(
            card.card_id for card in session.target_cards if card.simplified == "迷路"
        )
        updated = await store.record_assessment(
            session.session_id,
            assessed_card_id,
            comprehension=0.9,
            usage=0.9,
            assisted=False,
            evidence="学生独立正确地使用了这个词。",
        )
        assert updated.state == MasteryState.PRACTICING

        second = await store.import_cards(
            "learner-1", parse_pleco_xml(XML_V2), "second.xml"
        )
        assert second.updated_count == 1
        assert second.inactive_count == 1
        reimported = await store.get_deck("learner-1")
        active = reimported.cards[0]
        assert active.card_id == assessed_card_id
        assert active.mastery.state == MasteryState.PRACTICING

    asyncio.run(scenario())
