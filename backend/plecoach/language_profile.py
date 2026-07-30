"""Deterministic language-level inference for a Plecoach tutoring session."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .schemas import Card, TUTOR_SPEECH_LIMITS, TutorLanguageProfile

# Pleco folders in the learner's MCC export use the first form. The second form
# also accepts common user-created labels while requiring the HSK prefix, so a
# generic folder such as "Course/Level 4" cannot become proficiency evidence.
_HSK_30_LEVEL_RE = re.compile(
    r"\bHSK\s*3\.0(?:\s*[/_-]\s*|\s+)"
    r"(?:(?:Level|级别|等级)\s*)?"
    r"([1-9一二三四五六七八九])"
    r"(?:\s*[-–—]\s*[9九])?\s*级?(?!\d)",
    re.IGNORECASE,
)
_HSK_LEVEL_RE = re.compile(
    r"\bHSK(?!\s*3\.0)\s*(?:[/_-]\s*)?"
    r"(?:(?:Level|级别|等级)\s*)?"
    r"([1-9一二三四五六七八九])"
    r"(?:\s*[-–—]\s*[9九])?\s*级?(?!\d)",
    re.IGNORECASE,
)
_CHINESE_LEVELS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

_GRAMMAR_GUIDANCE: dict[int, str] = {
    1: (
        "只用最基本的主语、动词、宾语和常见时间地点说法；"
        "不用成语、书面语、把字句、被字句或抽象说法"
    ),
    2: (
        "只用常见日常语法，可以用一个“因为、所以、但是、如果”；"
        "不用成语、书面语、被字句或多层从句"
    ),
    3: (
        "使用常见口语语法和简单补语；复杂关系拆成两句，"
        "不用成语、文言式表达或连续从句"
    ),
    4: (
        "可以使用常见把字句、结果补语和简单复句，"
        "但不用生僻成语、正式书面词或多层从句"
    ),
    5: (
        "可以使用一般中级口语语法，但优先直接表达，"
        "避免生僻成语、专业术语和过长的修饰语"
    ),
    6: (
        "可以使用较丰富的自然口语，但避免不必要的书面语、"
        "专业术语和为了显得自然而堆叠的难词"
    ),
    7: (
        "可以使用高级自然口语，但仍要直接、具体，"
        "避免文学化、专业化或故意复杂的表达"
    ),
}


def hsk_level_from_category_paths(paths: Iterable[str]) -> int | None:
    """Return one conservative HSK level from a card or selected folder."""

    levels: set[int] = set()
    for path in paths:
        for pattern in (_HSK_30_LEVEL_RE, _HSK_LEVEL_RE):
            for match in pattern.findall(path):
                parsed = _CHINESE_LEVELS.get(match, int(match) if match.isdigit() else 0)
                if parsed:
                    # HSK 3.0 combines levels 7, 8, and 9 into one advanced band.
                    levels.add(min(parsed, 7))
    return min(levels) if levels else None


def _lower_median(values: Sequence[int]) -> int:
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _clean_support_word(value: str) -> str:
    flattened = _CONTROL_RE.sub("", value)
    return "".join(_HAN_RE.findall(flattened))[:12]


def infer_tutor_language_profile(
    cards: Sequence[Card],
    selected_category_paths: Sequence[str] = (),
) -> TutorLanguageProfile:
    """Infer a conservative profile from every active card in the chosen scope.

    Each card contributes at most one vote even when Pleco assigns it to several
    HSK folders. An explicitly selected HSK folder is authoritative. Otherwise
    the lower median resists a small number of advanced target-word outliers.
    """

    scoped_cards = [card for card in cards if card.active]
    leveled_cards = [
        (card, level)
        for card in scoped_cards
        if (level := hsk_level_from_category_paths(card.categories)) is not None
    ]
    per_card_levels = [level for _, level in leveled_cards]
    selected_levels = [
        hsk_level_from_category_paths((path,))
        for path in selected_category_paths
    ]
    recognized_selected_levels = [
        level for level in selected_levels if level is not None
    ]
    explicit_single_band = bool(recognized_selected_levels) and (
        len(selected_category_paths) == 1
        or (
            len(recognized_selected_levels) == len(selected_category_paths)
            and len(set(recognized_selected_levels)) == 1
        )
    )

    if explicit_single_band:
        scope_level = recognized_selected_levels[0]
        confidence = "high"
    elif per_card_levels:
        scope_level = _lower_median(per_card_levels)
        coverage = len(per_card_levels) / max(1, len(scoped_cards))
        if len(per_card_levels) >= 5 and coverage >= 0.5:
            confidence = "high"
        elif len(per_card_levels) >= 3 and coverage >= 0.25:
            confidence = "medium"
        else:
            confidence = "low"
    else:
        # Missing labels are not evidence of advanced proficiency. Begin at a
        # safe everyday level and let the tutor adapt from actual conversation.
        scope_level = 2
        confidence = "low"

    support_level = max(1, scope_level - 1)
    max_sentences, max_hanzi, max_clauses = TUTOR_SPEECH_LIMITS[support_level]
    support_words: list[str] = []
    seen_support_words: set[str] = set()
    for card, level in leveled_cards:
        word = _clean_support_word(card.simplified)
        if (
            level <= support_level
            and word
            and word not in seen_support_words
        ):
            seen_support_words.add(word)
            support_words.append(word)
            if len(support_words) == 40:
                break
    return TutorLanguageProfile(
        scope_hsk_level=scope_level,
        support_hsk_level=support_level,
        confidence=confidence,
        labeled_card_count=len(per_card_levels),
        scoped_card_count=len(scoped_cards),
        support_words=support_words,
        max_sentences=max_sentences,
        max_hanzi_per_sentence=max_hanzi,
        max_clauses=max_clauses,
    )


def build_language_profile_rules(profile: TutorLanguageProfile) -> str:
    """Render concrete, internal-only rules for the realtime tutor."""

    grammar = _GRAMMAR_GUIDANCE[profile.support_hsk_level]
    cleaned_support_words = list(
        dict.fromkeys(
            word
            for value in profile.support_words
            if (word := _clean_support_word(value))
        )
    )[:40]
    support_words = (
        "、".join(cleaned_support_words)
        if cleaned_support_words
        else "没有可靠的基础词列表，优先使用最常见的日常词"
    )
    pacing = (
        "语速放慢，词语之间清楚自然地停顿"
        if profile.support_hsk_level <= 2
        else "保持清楚、自然、不赶时间的语速"
    )
    return f"""
语言难度规则（最高优先级）：
- 这是内部教学设置，绝不能向学生宣布HSK、等级、难度估计或这些数字。
- 所选词库的典型难度大约为HSK {profile.scope_hsk_level}级；个别目标词可能更难，但它们是唯一允许超过支撑水平的词。
- 除目标词本身外，支撑语言始终按HSK {profile.support_hsk_level}级或更简单来表达。优先使用这些较容易的词：{support_words}。
- 每次最多说{profile.max_sentences}句，每句最多约{profile.max_hanzi_per_sentence}个汉字，最多{profile.max_clauses}个分句；一次只问一个问题，然后停下来等学生回答。
- {pacing}。
- {grammar}。
- 目标词可以较难，但解释目标词时只能描述一个具体动作、场景或简单例子。不要用一串更难的同义词解释，也不要照着英文词典释义翻译。
- 开始时严格使用这个较简单的水平。只有学生连续两轮轻松、切题地用完整句回答，下一轮才可以稍微增加一点复杂度，但支撑语言不得超过所选词库的典型水平。
- 如果学生说“听不懂”“什么意思”“请再说一次”，回答偏题，长时间卡住，或连续只说一两个词，立刻降级：每句不超过8个汉字，只给一个具体场景，并问一个二选一或很短的问题。
""".strip()
