from __future__ import annotations

import asyncio
import re

import pytest

from plecoach.agent import (
    PlecoachTutor,
    _endpointing_options,
    _tts_extra_kwargs,
)
from plecoach.language_profile import infer_tutor_language_profile
from plecoach.session_planner import SessionPlanner
from plecoach.schemas import (
    Card,
    Mastery,
    MasteryState,
    ParsedPlecoCard,
    PlecoStats,
    SessionRecord,
    TargetCard,
    TutorLanguageProfile,
)
from plecoach.store import MemoryStore
from plecoach.tutor import TutorContext, build_initial_greeting, build_tutor_instructions


def _hsk_path(level: int | str) -> str:
    return f"Archive/HSK 3.0/Level {level}"


def _card(
    card_id: str,
    *,
    word: str | None = None,
    categories: list[str] | None = None,
    pleco: PlecoStats | None = None,
    mastery: Mastery | None = None,
) -> Card:
    mastery = mastery or Mastery()
    return Card(
        card_id=card_id,
        simplified=word or f"词{card_id}",
        traditional=word or f"詞{card_id}",
        pinyin=f"ci2{card_id}",
        categories=categories or [],
        definition="test definition",
        pleco=pleco or PlecoStats(),
        mastery=mastery,
    )


def _target(card: Card) -> TargetCard:
    return TargetCard.from_card(card)


def _context(
    cards: list[TargetCard],
    profile: TutorLanguageProfile,
    *,
    topic: str = "用今天的词聊聊你的经历",
    selected_category_paths: tuple[str, ...] = ("新编会话/新编会话 1",),
) -> TutorContext:
    return TutorContext.from_value(
        {
            "session_id": "session-level-test",
            "learner_id": "learner-level-test",
            "selected_category_paths": list(selected_category_paths),
            "target_cards": [card.model_dump(mode="json") for card in cards],
            "language_profile": profile.model_dump(mode="json"),
            "topic": topic,
        },
        session_id="session-level-test",
        learner_id="learner-level-test",
    )


def _assert_bounded_profile(profile: TutorLanguageProfile) -> None:
    assert 1 <= profile.support_hsk_level <= profile.scope_hsk_level <= 7
    assert profile.max_sentences >= 1
    assert profile.max_hanzi_per_sentence >= 1
    assert profile.max_clauses >= 1


@pytest.mark.parametrize(
    ("category", "expected_level"),
    [
        ("Archive/HSK 3.0/Level 3", 3),
        ("Archive/HSK 3.0/Level 7-9", 7),
        ("Archive/HSK 3.0 Level 8", 7),
        ("Custom/HSK/Level 4", 4),
        ("Custom/HSK 5", 5),
        ("Custom/HSK 二级", 2),
    ],
)
def test_profile_recognizes_real_mcc_hsk_category_formats(
    category: str, expected_level: int
) -> None:
    profile = infer_tutor_language_profile(
        [_card("mcc", categories=[category])]
    )

    assert isinstance(profile, TutorLanguageProfile)
    assert profile.scope_hsk_level == expected_level
    assert profile.labeled_card_count == 1
    assert profile.scoped_card_count == 1
    _assert_bounded_profile(profile)


def test_profile_ignores_unrelated_bare_level_and_lesson_numbers() -> None:
    unrelated = [
        _card(
            "unrelated",
            categories=[
                "Course/Level 4",
                "Archive/当代中文二/当代中文二 10-1",
                "新编会话/新编会话 17",
            ],
        )
    ]
    unlabeled = [_card("unrelated")]

    actual = infer_tutor_language_profile(unrelated)
    baseline = infer_tutor_language_profile(unlabeled)

    assert actual == baseline
    assert actual.labeled_card_count == 0


def test_profile_counts_each_card_once_and_uses_its_lowest_hsk_tag() -> None:
    profile = infer_tutor_language_profile(
        [
            _card(
                "multi-label",
                categories=[
                    _hsk_path(5),
                    _hsk_path(2),
                    _hsk_path(2),
                ],
            )
        ]
    )

    assert profile.scope_hsk_level == 2
    assert profile.labeled_card_count == 1
    assert profile.scoped_card_count == 1


def test_profile_uses_conservative_lower_median_instead_of_high_outliers() -> None:
    cards = [
        _card(str(level), categories=[_hsk_path(level)])
        for level in (2, 3, 7, 7)
    ]

    profile = infer_tutor_language_profile(cards)

    assert profile.scope_hsk_level == 3
    assert profile.support_hsk_level == 2
    assert profile.labeled_card_count == 4
    assert profile.scoped_card_count == 4


def test_sparse_and_unlabeled_scopes_are_explicitly_low_confidence() -> None:
    sparse = infer_tutor_language_profile(
        [
            _card("labeled", categories=[_hsk_path(6)]),
            *[_card(f"unknown-{index}") for index in range(5)],
        ]
    )
    unlabeled = infer_tutor_language_profile(
        [_card(f"unknown-{index}") for index in range(6)]
    )

    assert sparse.confidence == "low"
    assert sparse.labeled_card_count == 1
    assert sparse.scoped_card_count == 6
    assert unlabeled.confidence == "low"
    assert unlabeled.labeled_card_count == 0
    assert unlabeled.scoped_card_count == 6
    _assert_bounded_profile(sparse)
    _assert_bounded_profile(unlabeled)


def test_explicit_selected_hsk_scope_overrides_card_level_estimate() -> None:
    cards = [
        _card("low", categories=[_hsk_path(2)]),
        _card("high", categories=[_hsk_path(7)]),
    ]

    profile = infer_tutor_language_profile(
        cards,
        selected_category_paths=("Archive/HSK 3.0/Level 4",),
    )

    assert profile.scope_hsk_level == 4
    assert profile.support_hsk_level == 3
    assert profile.confidence == "high"
    assert profile.labeled_card_count == 2
    assert profile.scoped_card_count == 2


def test_mixed_multi_folder_selection_uses_the_combined_card_scope() -> None:
    cards = [
        *[
            _card(f"low-{index}", categories=["Course/Scope", _hsk_path(2)])
            for index in range(3)
        ],
        _card("high", categories=[_hsk_path("7-9")]),
    ]

    profile = infer_tutor_language_profile(
        cards,
        selected_category_paths=("Course/Scope", _hsk_path("7-9")),
    )

    assert profile.scope_hsk_level == 2
    assert profile.support_hsk_level == 1
    assert profile.confidence == "medium"


def test_profile_persists_only_words_at_or_below_the_support_level() -> None:
    profile = infer_tutor_language_profile(
        [
            _card("easy", word="今天", categories=[_hsk_path(1)]),
            _card("matched", word="地图", categories=[_hsk_path(2)]),
            _card("hard", word="错综复杂", categories=[_hsk_path(7)]),
        ],
        selected_category_paths=(_hsk_path(2),),
    )

    assert profile.support_words == ["今天"]


def test_profile_is_independent_of_pleco_statistics_and_mastery() -> None:
    weak_history = [
        _card(
            "same",
            categories=[_hsk_path(3)],
            pleco=PlecoStats(
                score=0,
                difficulty=99,
                correct=0,
                incorrect=100,
                reviewed=100,
            ),
            mastery=Mastery(state=MasteryState.UNASSESSED),
        )
    ]
    strong_history = [
        _card(
            "same",
            categories=[_hsk_path(3)],
            pleco=PlecoStats(
                score=30_000,
                difficulty=1,
                correct=100,
                incorrect=0,
                reviewed=100,
            ),
            mastery=Mastery(
                state=MasteryState.FLUENT,
                comprehension_score=1,
                usage_score=1,
                assessment_count=20,
                independent_successes=20,
            ),
        )
    ]

    assert infer_tutor_language_profile(
        weak_history
    ) == infer_tutor_language_profile(strong_history)


def test_session_and_tutor_context_preserve_the_profile() -> None:
    scoped_cards = [_card("map", word="地图", categories=[_hsk_path(2)])]
    profile = infer_tutor_language_profile(scoped_cards)
    cards = [_target(card) for card in scoped_cards]
    session = SessionRecord(
        session_id="session-level-test",
        learner_id="learner-level-test",
        room_name="plecoach-level-test",
        selected_category_paths=["新编会话/新编会话 1"],
        target_cards=cards,
        topic_suggestions=["聊聊你的经历"],
        language_profile=profile,
    )

    restored = SessionRecord.model_validate_json(session.model_dump_json())
    context = TutorContext.from_value(
        restored,
        session_id=restored.session_id,
        learner_id=restored.learner_id,
    )

    assert restored.language_profile == profile
    assert context.language_profile == profile


def test_old_session_without_a_profile_loads_a_safe_default() -> None:
    card = _target(_card("map", word="地图"))
    restored = SessionRecord.model_validate(
        {
            "session_id": "old-session",
            "learner_id": "old-learner",
            "room_name": "plecoach-old-session",
            "selected_category_paths": [],
            "target_cards": [card.model_dump(mode="json")],
            "topic_suggestions": [],
        }
    )
    context = TutorContext.from_value(
        restored,
        session_id=restored.session_id,
        learner_id=restored.learner_id,
    )

    assert restored.language_profile == TutorLanguageProfile()
    assert context.language_profile == TutorLanguageProfile()


def test_profile_schema_rejects_internally_contradictory_values() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        TutorLanguageProfile(
            scope_hsk_level=2,
            support_hsk_level=3,
            max_sentences=2,
            max_hanzi_per_sentence=18,
            max_clauses=2,
        )
    with pytest.raises(ValueError, match="speech limits"):
        TutorLanguageProfile(max_hanzi_per_sentence=40)


def test_beginner_profile_slows_supported_tts_and_extends_endpointing() -> None:
    beginner = TutorLanguageProfile()
    advanced = TutorLanguageProfile(
        scope_hsk_level=6,
        support_hsk_level=5,
        max_sentences=3,
        max_hanzi_per_sentence=28,
        max_clauses=2,
    )

    assert _tts_extra_kwargs(beginner, "cartesia/sonic-3") == {"speed": "slow"}
    assert _tts_extra_kwargs(beginner, "custom/mandarin") == {}
    assert _tts_extra_kwargs(advanced, "cartesia/sonic-3") == {}
    assert _endpointing_options(beginner) == {
        "min_delay": 0.9,
        "max_delay": 4.0,
    }
    assert _endpointing_options(advanced) == {
        "min_delay": 0.5,
        "max_delay": 3.0,
    }


def test_prompt_enforces_the_profile_with_concrete_limits() -> None:
    scoped_cards = [
        _card("map", word="地图", categories=[_hsk_path(2)]),
        _card("lost", word="迷路", categories=[_hsk_path(2)]),
    ]
    profile = infer_tutor_language_profile(scoped_cards)
    cards = [_target(card) for card in scoped_cards]
    context = _context(cards, profile)

    prompt = build_tutor_instructions(context)
    agent_prompt = PlecoachTutor(context).instructions

    assert agent_prompt == prompt
    assert "语言难度规则" in prompt
    section = prompt.split("语言难度规则", 1)[1].split("\n\n", 1)[0]
    assert re.search(rf"词库[^\n]*{profile.scope_hsk_level}", section)
    assert f"按HSK {profile.support_hsk_level}级" in section
    assert f"{profile.max_sentences}句" in section
    assert f"{profile.max_hanzi_per_sentence}个汉字" in section
    assert f"{profile.max_clauses}个分句" in section


def test_hsk_one_support_uses_a_simpler_bounded_opening() -> None:
    scoped_cards = [_card("experience", word="经历", categories=[_hsk_path(2)])]
    profile = infer_tutor_language_profile(scoped_cards)
    cards = [_target(card) for card in scoped_cards]
    assert profile.support_hsk_level == 1
    context = _context(cards, profile, topic="用“经历”聊聊你的经历")

    greeting = build_initial_greeting(context)
    sentences = [
        sentence
        for sentence in re.split(r"(?<=[。！？])", greeting)
        if sentence.strip()
    ]

    assert "经历" not in greeting
    assert "分享" not in greeting
    assert greeting.endswith(("？", "?"))
    assert len(sentences) <= profile.max_sentences
    for sentence in sentences:
        assert len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", sentence)) <= (
            profile.max_hanzi_per_sentence
        )
        assert len(re.findall(r"[，；]", sentence)) + 1 <= profile.max_clauses


def test_hsk_one_story_opening_obeys_the_same_clause_limit() -> None:
    card = _card("story", word="故事", categories=[_hsk_path(2)])
    profile = infer_tutor_language_profile([card])
    context = _context([_target(card)], profile, topic="一起编一个小故事")

    greeting = build_initial_greeting(context)

    assert greeting == "你好。故事在家还是学校？"
    assert "，" not in greeting
    assert "；" not in greeting


def test_session_planner_profiles_the_full_selected_scope_not_only_six_targets() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        planner = SessionPlanner(store)
        beginner_cards = [
            ParsedPlecoCard(
                card_id=f"hsk2-{index}",
                simplified=f"基础词{index}",
                traditional=f"基礎詞{index}",
                pinyin=f"ji1chu3ci2{index}",
                categories=["Course/Scope", _hsk_path(2)],
                pleco=PlecoStats(
                    score=30_000,
                    correct=100,
                    incorrect=0,
                    reviewed=100,
                ),
            )
            for index in range(12)
        ]
        difficult_targets = [
            ParsedPlecoCard(
                card_id=f"hsk7-{index}",
                simplified=f"高级词{index}",
                traditional=f"高級詞{index}",
                pinyin=f"gao1ji2ci2{index}",
                categories=["Course/Scope", _hsk_path("7-9")],
                pleco=PlecoStats(
                    score=0,
                    correct=0,
                    incorrect=100,
                    reviewed=100,
                ),
            )
            for index in range(6)
        ]
        await store.import_cards(
            "profile-learner",
            [*beginner_cards, *difficult_targets],
            "profile.xml",
        )

        session = await planner.create_session(
            "profile-learner",
            ["Course/Scope"],
            target_count=6,
        )

        assert len(session.target_cards) == 6
        assert {
            card.card_id for card in session.target_cards
        } == {f"hsk7-{index}" for index in range(6)}
        assert session.language_profile.scope_hsk_level == 2
        assert session.language_profile.support_hsk_level == 1
        assert session.language_profile.labeled_card_count == 18
        assert session.language_profile.scoped_card_count == 18

    asyncio.run(scenario())
