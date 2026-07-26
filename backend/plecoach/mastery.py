"""Conversational mastery updates and adaptive card planning."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any, Iterable, Mapping, Sequence

from .schemas import (
    AssessmentEvidence,
    Card,
    CategoryNode,
    Mastery,
    MasteryState,
    MasterySummary,
    utc_now,
)

MAX_EVIDENCE_ITEMS = 20
PLANNING_ROTATION_PENALTY = 14.0
MAX_SELECTION_COUNT_GAP = 2


def _ewma(previous: float | None, observation: float, alpha: float = 0.45) -> float:
    if previous is None:
        return observation
    return (1 - alpha) * previous + alpha * observation


def update_mastery(
    mastery: Mastery,
    *,
    session_id: str,
    comprehension: float | None,
    usage: float | None,
    assisted: bool,
    evidence: str,
) -> Mastery:
    """Return a new mastery record from one conversational assessment.

    Pleco review values are deliberately absent from this function. A learner's
    Plecoach state can only move after evidence from a Plecoach conversation.
    """

    now = utc_now()
    comprehension_observation = comprehension
    usage_observation = usage

    # Hinted answers still show progress, but cannot look equivalent to an
    # independent response in either the score or the state transition.
    if assisted:
        if comprehension_observation is not None:
            comprehension_observation *= 0.85
        if usage_observation is not None:
            usage_observation *= 0.70

    comprehension_score = mastery.comprehension_score
    usage_score = mastery.usage_score
    if comprehension_observation is not None:
        comprehension_score = _ewma(comprehension_score, comprehension_observation)
    if usage_observation is not None:
        usage_score = _ewma(usage_score, usage_observation)

    independent_success = (
        not assisted
        and comprehension is not None
        and usage is not None
        and comprehension >= 0.70
        and usage >= 0.75
    )
    independent_successes = mastery.independent_successes + int(independent_success)
    successful_sessions = list(mastery.successful_session_ids)
    if independent_success and session_id not in successful_sessions:
        successful_sessions.append(session_id)

    assessment_count = mastery.assessment_count + 1
    lower_dimension = min(
        comprehension_score if comprehension_score is not None else 0.0,
        usage_score if usage_score is not None else 0.0,
    )
    if (
        independent_successes >= 3
        and len(successful_sessions) >= 2
        and lower_dimension >= 0.80
    ):
        state = MasteryState.FLUENT
        interval = timedelta(days=14)
    elif independent_successes >= 1 and lower_dimension >= 0.58:
        state = MasteryState.PRACTICING
        interval = timedelta(days=3 if independent_success else 1)
    else:
        state = MasteryState.LEARNING
        interval = timedelta(hours=12 if assisted or lower_dimension >= 0.45 else 4)

    item = AssessmentEvidence(
        session_id=session_id,
        comprehension=comprehension,
        usage=usage,
        assisted=assisted,
        evidence=evidence,
        created_at=now,
    )
    evidence_items = [*mastery.evidence, item][-MAX_EVIDENCE_ITEMS:]
    return mastery.model_copy(
        update={
            "state": state,
            "comprehension_score": comprehension_score,
            "usage_score": usage_score,
            "assessment_count": assessment_count,
            "independent_successes": independent_successes,
            "successful_session_ids": successful_sessions[-20:],
            "last_assessed_at": now,
            "next_review_at": now + interval,
            "evidence": evidence_items,
        }
    )


def _pleco_soft_signal(card: Card) -> float:
    """Return a deliberately capped priority contribution from Pleco history."""

    stats = card.pleco
    reviewed = stats.reviewed or 0
    incorrect = stats.incorrect or 0
    error_ratio = incorrect / reviewed if reviewed > 0 else 0.5
    no_history = 1.0 if reviewed == 0 else 0.0
    low_score = 1.0
    if stats.score is not None:
        low_score = max(0.0, min(1.0, 1 - stats.score / 30_000))
    # Range: 0–12. Mastery/due state contributes tens of points.
    return 7 * error_ratio + 3 * no_history + 2 * low_score


def planning_priority(card: Card) -> float:
    """Rank a card for the next session, prioritizing Plecoach evidence."""

    now = utc_now()
    state_base = {
        MasteryState.UNASSESSED: 100.0,
        MasteryState.LEARNING: 90.0,
        MasteryState.PRACTICING: 55.0,
        MasteryState.FLUENT: 12.0,
    }[card.mastery.state]

    due_signal = 0.0
    if card.mastery.state != MasteryState.UNASSESSED:
        next_review = card.mastery.next_review_at
        if next_review is None or next_review <= now:
            due_signal = 35.0
        else:
            days_until_due = (next_review - now).total_seconds() / 86_400
            due_signal = -min(20.0, days_until_due * 4)

    # Stable jitter prevents XML ordering from always deciding ties.
    jitter = int(hashlib.sha256(card.card_id.encode()).hexdigest()[:4], 16) / 65_535
    return state_base + due_signal + _pleco_soft_signal(card) + jitter


def card_matches_categories(card: Card, selected_paths: Sequence[str]) -> bool:
    if not selected_paths:
        return True
    for selected in selected_paths:
        normalized = selected.strip().strip("/")
        if not normalized:
            continue
        if any(
            category == normalized or category.startswith(normalized + "/")
            for category in card.categories
        ):
            return True
    return False


def select_target_cards(
    cards: Iterable[Card],
    selected_paths: Sequence[str],
    target_count: int,
    recent_target_card_ids: Sequence[str] = (),
    target_selection_counts: Mapping[str, int] | None = None,
) -> list[Card]:
    eligible = [
        card
        for card in cards
        if card.active and card_matches_categories(card, selected_paths)
    ]

    # Planning recency is deliberately separate from mastery: merely seeing a
    # card in a preview is not evidence that the learner understands or uses it.
    # A one-count/last-plan penalty is stronger than the capped Pleco signal
    # within a mastery tier, but weaker than a genuinely due learning boost.
    selection_counts = target_selection_counts or {}
    minimum_selection_count = min(
        (selection_counts.get(card.card_id, 0) for card in eligible),
        default=0,
    )
    recent_target_ids = set(recent_target_card_ids)

    def priority_with_cooldown(card: Card) -> float:
        count_gap = max(
            0,
            selection_counts.get(card.card_id, 0) - minimum_selection_count,
        )
        penalty = (
            min(count_gap, MAX_SELECTION_COUNT_GAP) * PLANNING_ROTATION_PENALTY
        )
        if card.card_id in recent_target_ids:
            penalty = max(penalty, PLANNING_ROTATION_PENALTY)
        return planning_priority(card) - penalty

    eligible.sort(key=priority_with_cooldown, reverse=True)
    return eligible[:target_count]


def summarize_mastery(cards: Iterable[Card]) -> MasterySummary:
    counts = {state: 0 for state in MasteryState}
    for card in cards:
        if card.active:
            counts[card.mastery.state] += 1
    return MasterySummary(
        unassessed=counts[MasteryState.UNASSESSED],
        learning=counts[MasteryState.LEARNING],
        practicing=counts[MasteryState.PRACTICING],
        fluent=counts[MasteryState.FLUENT],
    )


def build_category_tree(cards: Iterable[Card]) -> list[CategoryNode]:
    """Build a hierarchy with de-duplicated card counts at every branch."""

    roots: dict[str, dict[str, Any]] = {}
    for card in cards:
        if not card.active:
            continue
        for category_path in card.categories:
            parts = [part for part in category_path.split("/") if part]
            siblings = roots
            path_parts: list[str] = []
            for index, part in enumerate(parts):
                path_parts.append(part)
                node = siblings.setdefault(
                    part,
                    {
                        "name": part,
                        "path": "/".join(path_parts),
                        "all_cards": set(),
                        "direct_cards": set(),
                        "children": {},
                    },
                )
                node["all_cards"].add(card.card_id)
                if index == len(parts) - 1:
                    node["direct_cards"].add(card.card_id)
                siblings = node["children"]

    def convert(nodes: dict[str, dict[str, Any]]) -> list[CategoryNode]:
        converted: list[CategoryNode] = []
        for raw in sorted(nodes.values(), key=lambda item: item["name"].casefold()):
            converted.append(
                CategoryNode(
                    name=raw["name"],
                    path=raw["path"],
                    card_count=len(raw["all_cards"]),
                    direct_card_count=len(raw["direct_cards"]),
                    children=convert(raw["children"]),
                )
            )
        return converted

    return convert(roots)


def suggest_topics(targets: Sequence[Card], selected_paths: Sequence[str]) -> list[str]:
    """Create deterministic Mandarin prompts without adding an LLM call to setup."""

    target_words = "、".join(card.simplified for card in targets[:3])
    leaf = selected_paths[0].rstrip("/").rsplit("/", 1)[-1] if selected_paths else ""
    suggestions: list[str] = []
    if leaf:
        suggestions.append(f"围绕“{leaf}”聊一个真实生活场景")
    if target_words:
        suggestions.append(f"用“{target_words}”聊聊你的经历")
    suggestions.append("一起编一个小故事，自然地用上今天的词")
    return list(dict.fromkeys(suggestions))[:3]
