from __future__ import annotations

from fastapi.testclient import TestClient

from plecoach import api
from plecoach.store import MemoryStore


XML = b"""<plecoflash formatversion="2"><cards>
  <card><entry>
    <headword charset="sc">&#28857;&#33756;</headword>
    <headword charset="tc">&#40670;&#33756;</headword>
    <pron type="hypy">dian3cai4</pron>
  </entry><catassign category="Food/Restaurant"/></card>
</cards></plecoflash>"""


def test_full_setup_contract(monkeypatch) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setattr(api, "_connection_token", lambda **_: "signed-token")
    application = api.create_app(MemoryStore())

    with TestClient(application) as client:
        health = client.get("/api/health")
        assert health.status_code == 200

        imported = client.post(
            "/api/decks/import",
            data={"learner_id": "browser-user"},
            files={"file": ("sample.xml", XML, "application/xml")},
        )
        assert imported.status_code == 200
        assert imported.json()["card_count"] == 1

        deck = client.get("/api/decks/browser-user")
        assert deck.status_code == 200
        assert deck.json()["category_tree"][0]["path"] == "Food"

        planned = client.post(
            "/api/sessions",
            json={
                "learner_id": "browser-user",
                "category_paths": ["Food"],
                "target_count": 6,
            },
        )
        assert planned.status_code == 201
        session_id = planned.json()["session_id"]
        assert planned.json()["target_cards"][0]["simplified"] == "点菜"
        assert planned.json()["topic_suggestions"]

        connection = client.post(
            f"/api/sessions/{session_id}/connection",
            json={"topic": "在餐厅点菜"},
        )
        assert connection.status_code == 200
        assert connection.json()["token"] == "signed-token"
        assert connection.json()["participant_token"] == "signed-token"

        saved = client.get(f"/api/sessions/{session_id}")
        assert saved.json()["topic"] == "在餐厅点菜"

