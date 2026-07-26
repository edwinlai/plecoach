"""Safe, narrowly scoped parser for Pleco flashcard XML exports."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET

from .schemas import ParsedPlecoCard, PlecoStats

MAX_XML_BYTES = 10 * 1024 * 1024


class PlecoParseError(ValueError):
    """Raised when an upload is not a usable Pleco XML export."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _first_child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element if _local_name(child.tag) == name), None)


def _clean_text(text: str | None) -> str:
    return unicodedata.normalize("NFC", (text or "").strip())


def normalize_category_path(raw_path: str) -> str:
    """Normalize separators without flattening Pleco's hierarchy."""

    parts = [_clean_text(part) for part in raw_path.replace("\\", "/").split("/")]
    return "/".join(part for part in parts if part)


def make_card_id(simplified: str, pinyin: str) -> str:
    """Create a stable merge key from the fields a Pleco user can recognize."""

    normalized = "\x1f".join(
        (
            unicodedata.normalize("NFKC", simplified).strip(),
            re.sub(r"\s+", "", unicodedata.normalize("NFKC", pinyin)).casefold(),
        )
    )
    return "card_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_stats(score_info: ET.Element | None) -> PlecoStats:
    if score_info is None:
        return PlecoStats()
    attrs = score_info.attrib
    return PlecoStats(
        scorefile=attrs.get("scorefile"),
        score=_optional_int(attrs.get("score")),
        difficulty=_optional_int(attrs.get("difficulty")),
        history=attrs.get("history"),
        correct=_optional_int(attrs.get("correct")),
        incorrect=_optional_int(attrs.get("incorrect")),
        reviewed=_optional_int(attrs.get("reviewed")),
        since_last=_optional_int(attrs.get("sincelast")),
        first_reviewed_at=_optional_int(attrs.get("firstreviewedtime")),
        last_reviewed_at=_optional_int(attrs.get("lastreviewedtime")),
    )


def _parse_card(card_element: ET.Element) -> ParsedPlecoCard | None:
    entry = _first_child(card_element, "entry")
    if entry is None:
        return None

    headwords: dict[str, str] = {}
    first_headword = ""
    pinyin = ""
    for child in entry:
        child_name = _local_name(child.tag)
        if child_name == "headword":
            value = _clean_text(child.text)
            if not value:
                continue
            first_headword = first_headword or value
            headwords[child.attrib.get("charset", "").casefold()] = value
        elif child_name == "pron" and (
            not pinyin or child.attrib.get("type", "").casefold() == "hypy"
        ):
            pinyin = _clean_text(child.text)

    simplified = headwords.get("sc") or first_headword or headwords.get("tc", "")
    traditional = headwords.get("tc") or simplified
    if not simplified:
        return None

    categories: list[str] = []
    seen_categories: set[str] = set()
    for assignment in _children(card_element, "catassign"):
        category = normalize_category_path(assignment.attrib.get("category", ""))
        if category and category not in seen_categories:
            seen_categories.add(category)
            categories.append(category)

    return ParsedPlecoCard(
        card_id=make_card_id(simplified, pinyin),
        simplified=simplified,
        traditional=traditional,
        pinyin=pinyin,
        categories=categories,
        pleco=_parse_stats(_first_child(card_element, "scoreinfo")),
        pleco_created_at=_optional_int(card_element.attrib.get("created")),
        pleco_modified_at=_optional_int(card_element.attrib.get("modified")),
    )


def parse_pleco_xml(xml_bytes: bytes) -> list[ParsedPlecoCard]:
    """Parse a Pleco format-version 2 export into deduplicated cards.

    Standard-library ElementTree does not fetch external resources, and explicit
    declarations are rejected as defense in depth. The API also applies the same
    size limit before invoking this function.
    """

    if not xml_bytes:
        raise PlecoParseError("The uploaded file is empty.")
    if len(xml_bytes) > MAX_XML_BYTES:
        raise PlecoParseError("The Pleco XML file must be 10 MB or smaller.")

    upper_prefix = xml_bytes[:100_000].upper()
    if b"<!DOCTYPE" in upper_prefix or b"<!ENTITY" in upper_prefix:
        raise PlecoParseError("XML document type and entity declarations are not supported.")

    try:
        root = ET.fromstring(xml_bytes)
    except (ET.ParseError, ValueError) as exc:
        raise PlecoParseError("The file is not valid XML.") from exc

    if _local_name(root.tag) != "plecoflash":
        raise PlecoParseError("The file is not a Pleco flashcard export.")

    cards_container = _first_child(root, "cards")
    if cards_container is None:
        raise PlecoParseError("The Pleco export does not contain a cards section.")

    cards_by_id: dict[str, ParsedPlecoCard] = {}
    for card_element in _children(cards_container, "card"):
        parsed = _parse_card(card_element)
        if parsed is None:
            continue
        prior = cards_by_id.get(parsed.card_id)
        if prior is None:
            cards_by_id[parsed.card_id] = parsed
            continue

        # Pleco can contain duplicate word/pronunciation records. The tutoring
        # unit is the word, so retain one card and union every category path.
        categories = list(dict.fromkeys([*prior.categories, *parsed.categories]))
        prefer_new = (parsed.pleco_modified_at or 0) >= (prior.pleco_modified_at or 0)
        winner = parsed if prefer_new else prior
        cards_by_id[parsed.card_id] = winner.model_copy(update={"categories": categories})

    if not cards_by_id:
        raise PlecoParseError("No usable Chinese flashcards were found in the export.")
    return list(cards_by_id.values())

