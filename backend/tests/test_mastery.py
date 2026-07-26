from __future__ import annotations

from datetime import timedelta

from plecoach.mastery import select_target_cards
from plecoach.schemas import Card, Mastery, MasteryState, utc_now


def card(
    card_id: str,
    *,
    mastery: Mastery | None = None,
) -> Card:
    return Card(
        card_id=card_id,
        simplified=card_id,
        traditional=card_id,
        pinyin="ci2",
        categories=["Course/Lesson"],
        mastery=mastery or Mastery(),
    )


def test_recent_due_learning_card_can_still_outrank_fresh_unassessed_card() -> None:
    due = card(
        "due",
        mastery=Mastery(
            state=MasteryState.LEARNING,
            next_review_at=utc_now() - timedelta(minutes=1),
        ),
    )
    fresh = card("fresh")

    selected = select_target_cards(
        [due, fresh],
        ["Course/Lesson"],
        1,
        recent_target_card_ids=[due.card_id],
    )

    assert selected[0].card_id == due.card_id


def test_small_pool_returns_each_card_once_even_when_all_are_recent() -> None:
    cards = [card(f"card-{index}") for index in range(3)]

    selected = select_target_cards(
        cards,
        ["Course"],
        6,
        recent_target_card_ids=[item.card_id for item in cards],
    )

    assert len(selected) == 3
    assert len({item.card_id for item in selected}) == 3
