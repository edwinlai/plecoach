from __future__ import annotations

import pytest

from plecoach.pleco_parser import (
    MAX_DEFINITION_CHARS,
    PlecoParseError,
    parse_pleco_xml,
)


def test_parser_preserves_hierarchy_and_merges_duplicate_categories() -> None:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <plecoflash formatversion="2">
      <cards>
        <card created="1" modified="2">
          <entry>
            <headword charset="sc">&#36855;&#36335;</headword>
            <headword charset="tc">&#36855;&#36335;</headword>
            <pron type="hypy" tones="numbers">mi2lu4</pron>
            <defn>
              to get <b>lost</b>
              while traveling
            </defn>
          </entry>
          <catassign category="Travel/Directions"/>
          <scoreinfo score="1200" correct="1" incorrect="2" reviewed="3"/>
        </card>
        <card created="1" modified="3">
          <entry>
            <headword charset="sc">&#36855;&#36335;</headword>
            <headword charset="tc">&#36855;&#36335;</headword>
            <pron type="hypy" tones="numbers">mi2lu4</pron>
          </entry>
          <catassign category="Course/Week 1"/>
        </card>
      </cards>
    </plecoflash>"""

    cards = parse_pleco_xml(xml)

    assert len(cards) == 1
    assert cards[0].simplified == "迷路"
    assert cards[0].pinyin == "mi2lu4"
    assert cards[0].definition == "to get lost while traveling"
    assert cards[0].categories == ["Travel/Directions", "Course/Week 1"]


def test_parser_bounds_whitespace_normalized_definition() -> None:
    long_definition = " ".join(["词义"] * (MAX_DEFINITION_CHARS + 100))
    xml = f"""<plecoflash formatversion="2"><cards><card><entry>
      <headword charset="sc">测试</headword>
      <pron type="hypy">ce4shi4</pron>
      <defn><sense>{long_definition}</sense></defn>
    </entry></card></cards></plecoflash>""".encode()

    card = parse_pleco_xml(xml)[0]

    assert len(card.definition) == MAX_DEFINITION_CHARS
    assert "\n" not in card.definition
    assert "  " not in card.definition


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"", "empty"),
        (b"<not-pleco/>", "not a Pleco"),
        (b"<!DOCTYPE foo><plecoflash><cards/></plecoflash>", "not supported"),
        (b"<plecoflash>", "not valid XML"),
    ],
)
def test_parser_rejects_invalid_uploads(payload: bytes, message: str) -> None:
    with pytest.raises(PlecoParseError, match=message):
        parse_pleco_xml(payload)
