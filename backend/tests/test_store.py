from __future__ import annotations

import asyncio

from plecoach.pleco_parser import parse_pleco_xml
from plecoach.schemas import MasteryState
from plecoach.store import MemoryStore


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


def test_import_session_assessment_and_reimport_preserve_plecoach_mastery() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        first = await store.import_cards("learner-1", parse_pleco_xml(XML_V1), "first.xml")
        assert first.added_count == 2
        assert first.mastery_summary.unassessed == 2

        deck = await store.get_deck("learner-1")
        assert all(card.mastery.state == MasteryState.UNASSESSED for card in deck.cards)
        travel = next(node for node in deck.category_tree if node.path == "Travel")
        assert travel.path == "Travel"
        assert travel.card_count == 2
        assert travel.children[0].path == "Travel/Directions"

        session = await store.create_session(
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


def test_parent_category_selects_descendants_without_duplicate_targets() -> None:
    async def scenario() -> None:
        store = MemoryStore()
        await store.import_cards("learner", parse_pleco_xml(XML_V1), "deck.xml")
        session = await store.create_session("learner", ["Travel"], target_count=10)
        assert len(session.target_cards) == 2
        assert len({card.card_id for card in session.target_cards}) == 2

    asyncio.run(scenario())
