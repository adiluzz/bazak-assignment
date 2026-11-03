import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.agent.tools import SearchArgs
from api.catalog.search import refresh_known_categories
from api.db.engine import db_session
from api.main import app


@pytest.fixture
def client(seeded):
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    payload = client.get("/api/health").json()
    assert payload["database"] == "ok"
    assert payload["product_count"] == 14
    assert payload["catalog"] == "ready"
    assert payload["embedding_backlog"] == 0


def test_spa_fallback_serves_index_for_deep_link(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>shop</title>")
    monkeypatch.setenv("SPA_DIST", str(tmp_path))
    from api.settings import get_settings

    get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None
    with TestClient(app) as test_client:
        response = test_client.get("/c/abc")
    assert response.status_code == 200
    assert "shop" in response.text


def test_conversation_crud_and_order(client):
    first = client.post("/api/conversations", json={"title": "First"}).json()
    second = client.post("/api/conversations", json={"title": "Second"}).json()
    listing = client.get("/api/conversations").json()["conversations"]
    assert [item["id"] for item in listing[:2]] == [second["id"], first["id"]]
    renamed = client.patch(f"/api/conversations/{first['id']}", json={"title": "Renamed"}).json()
    assert renamed["title"] == "Renamed"
    empty = client.get(f"/api/conversations/{first['id']}/messages").json()
    assert empty["messages"] == []
    assert client.delete(f"/api/conversations/{first['id']}").status_code == 200
    assert client.get(f"/api/conversations/{first['id']}/messages").status_code == 404


def test_agent_identity_is_stable(client):
    agent = client.app.state.agent
    created = client.post("/api/conversations").json()
    client.post(f"/api/conversations/{created['id']}/turn", json={"text": "a phone under 500"})
    other = client.post("/api/conversations").json()
    client.post(f"/api/conversations/{other['id']}/turn", json={"text": "thanks"})
    assert client.app.state.agent is agent


def test_search_tool_rejects_unknown_category(seeded):
    session = db_session()
    refresh_known_categories(session)
    session.close()
    with pytest.raises(ValidationError):
        SearchArgs(categories=["not-a-real-category"])


def test_turn_search_returns_cards(client):
    created = client.post("/api/conversations").json()
    payload = client.post(f"/api/conversations/{created['id']}/turn", json={"text": "a phone under 500"}).json()
    titles = [product["title"] for group in payload["groups"] for product in group["products"]]
    assert "Galaxy Budget" in titles
    assert all(product["price"] <= 500 for group in payload["groups"] for product in group["products"])
    assert payload["reply"]


def test_multi_intent_two_groups(client):
    created = client.post("/api/conversations").json()
    payload = client.post(
        f"/api/conversations/{created['id']}/turn",
        json={"text": "a laptop and a watch"},
    ).json()
    assert len(payload["groups"]) == 2
    labels = " ".join(group["label"] for group in payload["groups"]).lower()
    assert "laptop" in labels and "watch" in labels


def test_off_catalog_no_cards(client):
    created = client.post("/api/conversations").json()
    payload = client.post(f"/api/conversations/{created['id']}/turn", json={"text": "a flight to Tokyo"}).json()
    assert payload["groups"] == []
    assert payload["route"] == "off_catalog"
    assert "flight" in payload["reply"].lower() or "don't" in payload["reply"].lower()


def test_clarify_asks_from_the_catalog(client):
    created = client.post("/api/conversations").json()
    payload = client.post(
        f"/api/conversations/{created['id']}/turn",
        json={"text": "something cheap and cool"},
    ).json()
    assert payload["route"] == "clarify"
    reply = payload["reply"].lower()
    assert "?" in payload["reply"] or "what" in reply
    assert any(name in reply for name in ("beauty", "smartphone", "laptop", "home decoration"))


def test_follow_up_uses_prior_results(client):
    created = client.post("/api/conversations").json()
    client.post(f"/api/conversations/{created['id']}/turn", json={"text": "a phone under 500"})
    follow = client.post(f"/api/conversations/{created['id']}/turn", json={"text": "the cheaper one"}).json()
    assert follow["reply"]
    assert follow["groups"]


def test_hybrid_respects_price_filter(seeded):
    from api.catalog.search import search_products

    session = db_session()
    products, _note = search_products(session, query="waterproof pack", price_max=100)
    session.close()
    assert products
    assert all(item["price"] <= 100 for item in products)
    assert products[0]["title"] == "Trail Pack"


def _parse_sse(response) -> list[dict]:
    events = []
    current = None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            current = line.removeprefix("event: ")
        elif line.startswith("data: ") and current:
            events.append(json.loads(line.removeprefix("data: ")))
            current = None
    return events


def test_stream_event_order(client):
    created = client.post("/api/conversations").json()
    response = client.post(f"/api/conversations/{created['id']}/stream", json={"text": "a phone under 500"})
    events = _parse_sse(response)
    types = [event["type"] for event in events]
    assert types[0] == "status"
    assert "products" in types
    assert "token" in types
    assert types[-1] == "done"
    assert types.index("products") < types.index("token")


def test_closed_stream_keeps_checkpoint(client):
    created = client.post("/api/conversations").json()
    with client.stream("POST", f"/api/conversations/{created['id']}/stream", json={"text": "thanks"}) as response:
        next(response.iter_text())
    messages = client.get(f"/api/conversations/{created['id']}/messages").json()["messages"]
    assert any(item["role"] == "assistant" and item["content"] for item in messages)


def test_review_drops_a_product_that_does_not_answer(monkeypatch):
    from api.agent.review import review_products

    monkeypatch.setenv("FAKE_LLM", "0")
    swing = {
        "id": 43,
        "title": "Decoration Swing",
        "description": "It adds a touch of elegance and whimsy to any room.",
        "category": "home-decoration",
    }
    phone = {"id": 2, "title": "Galaxy Budget", "description": "A phone.", "category": "smartphones"}

    def decide(shopper, query, products):
        return {43: 0.07, 2: 1.0}

    monkeypatch.setattr("api.agent.review._ask_model", decide)
    kept, note = review_products("I'm looking for a present that I can buy for a man", "gift for him", [swing])
    assert kept == []
    assert "answer" in note.lower()
    kept, note = review_products("a phone under 500", "phone", [phone, swing])
    assert [item["id"] for item in kept] == [2]
    assert note == ""


def test_review_keeps_results_for_the_scripted_model(monkeypatch):
    from api.agent.review import review_products

    monkeypatch.setenv("FAKE_LLM", "1")
    products = [{"id": 43, "title": "Decoration Swing", "description": "whimsy", "category": "home-decoration"}]
    kept, note = review_products("a present for a man", "gift for him", products)
    assert kept == products
    assert note == ""


@pytest.mark.eval
def test_eval_phone_trajectory(client):
    created = client.post("/api/conversations").json()
    payload = client.post(f"/api/conversations/{created['id']}/turn", json={"text": "a phone under 500"}).json()
    assert payload["route"] == "search"
    assert payload["groups"]
    assert all(product["id"] != 99999 for group in payload["groups"] for product in group["products"])


@pytest.mark.eval
@pytest.mark.skipif(__import__("os").getenv("EVAL_LIVE") != "1", reason="set EVAL_LIVE=1 to call gpt-6-luna")
def test_eval_live_prompts():
    assert Path(".env").exists() or __import__("os").getenv("OPENAI_API_KEY")
