"""Deterministic, session-local detection of learner-spoken target words."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Protocol


class FocusTarget(Protocol):
    card_id: str
    simplified: str
    traditional: str | None


def normalize_spoken_text(value: str) -> str:
    """Remove spacing and punctuation that STT may insert between Hanzi."""

    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
        and not unicodedata.category(character).startswith(("P", "Z"))
    )


def find_spoken_target_card_ids(
    text: str,
    target_cards: Iterable[FocusTarget],
) -> list[str]:
    """Return target IDs whose simplified or traditional form occurs in text."""

    normalized_text = normalize_spoken_text(text)
    if not normalized_text:
        return []

    matches: list[str] = []
    for card in target_cards:
        forms = {
            normalize_spoken_text(card.simplified),
            normalize_spoken_text(card.traditional or ""),
        }
        if any(form and form in normalized_text for form in forms):
            matches.append(card.card_id)
    return matches
