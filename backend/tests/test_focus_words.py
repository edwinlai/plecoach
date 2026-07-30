from __future__ import annotations

import asyncio

from plecoach.agent import TutorRuntime
from plecoach.focus_words import find_spoken_target_card_ids
from plecoach.schemas import (
    Mastery,
    MasteryState,
    PlanningState,
    SessionRecord,
    TargetCard,
)
from plecoach.store import MemoryStore
from plecoach.tutor import TutorContext


def _target(
    card_id: str,
    simplified: str,
    traditional: str | None = None,
) -> TargetCard:
    return TargetCard(
        card_id=card_id,
        simplified=simplified,
        traditional=traditional or simplified,
        pinyin="",
        categories=[],
        mastery_state=MasteryState.UNASSESSED,
        mastery=Mastery(),
    )


def test_matches_simplified_traditional_and_stt_spacing() -> None:
    targets = [
        _target("map", "地图", "地圖"),
        _target("lost", "迷路"),
        _target("ride", "搭便车", "搭便車"),
    ]

    assert find_spoken_target_card_ids(
        "我看地 圖，也迷路了，还想搭 便车。",
        targets,
    ) == ["map", "lost", "ride"]


def test_unrelated_text_does_not_match_targets() -> None:
    assert find_spoken_target_card_ids(
        "我今天坐地铁去公园。",
        [_target("map", "地图", "地圖")],
    ) == []


def test_student_mentions_are_persisted_monotonically_without_changing_mastery() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        session = SessionRecord(
            session_id="session-focus",
            learner_id="learner-focus",
            room_name="room-focus",
            selected_category_paths=[],
            target_cards=[
                _target("map", "地图", "地圖"),
                _target("lost", "迷路"),
            ],
            topic_suggestions=[],
        )
        await store.save_plan(
            PlanningState(learner_id="learner-focus"),
            session,
        )

        await store.append_transcript("session-focus", "tutor", "请看地图。")
        assert (
            await store.get_session("session-focus")
        ).learner_spoken_target_card_ids == []

        await store.append_transcript(
            "session-focus",
            "student",
            "我看地 圖，但是还是迷路了。",
        )
        await store.append_transcript(
            "session-focus",
            "student",
            "后来我找到地方了。",
        )
        await store.append_transcript(
            "session-focus",
            "student",
            "地图让我不迷路。",
        )

        updated = await store.get_session("session-focus")
        assert updated.learner_spoken_target_card_ids == ["map", "lost"]
        assert all(
            card.mastery.state == MasteryState.UNASSESSED
            for card in updated.target_cards
        )

    asyncio.run(scenario())


def test_existing_sessions_without_spoken_ids_remain_compatible() -> None:
    session = SessionRecord.model_validate(
        {
            "session_id": "old-session",
            "learner_id": "learner",
            "room_name": "room",
            "selected_category_paths": [],
            "target_cards": [],
            "topic_suggestions": [],
        }
    )

    assert session.learner_spoken_target_card_ids == []


def test_runtime_publishes_committed_student_mentions_only() -> None:
    class RecordingStore:
        def __init__(self) -> None:
            self.turns: list[tuple[str, str]] = []

        async def append_transcript(self, _session_id, role, text):
            self.turns.append((role, text))
            return text

    async def scenario() -> tuple[RecordingStore, list[dict[str, object]]]:
        store = RecordingStore()
        events: list[dict[str, object]] = []
        context = TutorContext.from_value(
            {
                "target_cards": [
                    {
                        "card_id": "map",
                        "simplified": "地图",
                        "traditional": "地圖",
                    }
                ]
            },
            session_id="session-focus",
            learner_id="learner-focus",
        )

        async def publish(payload: dict[str, object]) -> None:
            events.append(payload)

        runtime = TutorRuntime(
            context=context,
            store=store,
            publish_event=publish,
        )
        await runtime.persist_transcript("tutor", "你可以看看地图。")
        await runtime.persist_transcript("student", "好，我看看地圖。")
        return store, events

    store, events = asyncio.run(scenario())

    assert store.turns == [
        ("tutor", "你可以看看地图。"),
        ("student", "好，我看看地圖。"),
    ]
    assert events == [
        {
            "type": "learner_spoken_targets",
            "card_ids": ["map"],
        }
    ]
