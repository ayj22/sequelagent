import httpx
import pytest
from fastapi.testclient import TestClient

from analyst import agent, api, overview, present, warehouse
from analyst.limits import RateLimit
from analyst.llm import ModelError, OpenAIModel
from conftest import FakeModel


def test_model_errors_never_echo_the_provider_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    reply = httpx.Response(401, json={"error": {"message": "Incorrect API key provided: test-k**y"}})
    model = OpenAIModel("m", client=httpx.Client(transport=httpx.MockTransport(lambda r: reply)))
    with pytest.raises(ModelError) as caught:
        model.complete([{"role": "user", "content": "q"}])
    assert "401" in str(caught.value) and "test-k" not in str(caught.value)


@pytest.mark.parametrize("address", ["http://example.com/v1", "ftp://example.com", "example.com"])
def test_the_key_is_only_sent_over_https(address, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", address)
    with pytest.raises(ModelError):
        OpenAIModel("m")


@pytest.mark.parametrize("body", [b"<html>gateway</html>", b'{"choices": []}', b'{"error": "x"}', b"[]"])
def test_an_unreadable_model_reply_is_a_plain_error(body, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=body))
    with pytest.raises(ModelError):
        OpenAIModel("m", client=httpx.Client(transport=transport)).complete([{"role": "user", "content": "q"}])


def test_api_without_a_key_says_so(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SEQUELAGENT_API_TOKEN", raising=False)
    monkeypatch.setattr(api, "load_env", lambda: None)
    monkeypatch.setattr(api, "limiter", RateLimit(calls=5, seconds=60))
    api.get_model.cache_clear()
    response = TestClient(api.app).post("/ask", json={"question": "q"})
    assert response.status_code == 503 and "OPENAI_API_KEY" in response.json()["detail"]


def test_rate_limit_window():
    now = [0.0]
    limit = RateLimit(calls=2, seconds=10, clock=lambda: now[0])
    assert limit.allow() and limit.allow() and not limit.allow()
    now[0] = 10.0
    assert limit.allow()


def test_api_token_and_limit(monkeypatch):
    monkeypatch.setenv("SEQUELAGENT_API_TOKEN", "s3cret")
    monkeypatch.setattr(api, "limiter", RateLimit(calls=1, seconds=60))
    api.app.dependency_overrides[api.get_model] = lambda: FakeModel("CANNOT_ANSWER: no")
    try:
        client = TestClient(api.app)
        assert client.post("/ask", json={"question": "q"}).status_code == 401
        assert client.post("/ask", json={"question": "q"}, headers={"Authorization": "Bearer nope"}).status_code == 401
        good = {"Authorization": "Bearer s3cret"}
        assert client.post("/ask", json={"question": "q"}, headers=good).status_code == 200
        assert client.post("/ask", json={"question": "q"}, headers=good).status_code == 429
    finally:
        api.app.dependency_overrides.clear()


@pytest.mark.parametrize("text", ["=HYPERLINK(1)", "+1", "-2+3", "@cmd", "  =x"])
def test_spreadsheet_formulas_are_neutralised(text):
    assert present.spreadsheet_safe(text).startswith("'")


def test_numbers_and_ordinary_text_are_untouched():
    assert present.spreadsheet_safe(-5) == -5 and present.spreadsheet_safe("West") == "West"


def test_model_text_cannot_inject_markup_into_the_screen(db, monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(warehouse, "DB_PATH", db)
    evil = "CANNOT_ANSWER: x\n\n![t](https://evil.example/?q=1) <img src=x onerror=alert(1)>"
    screen = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "analyst" / "app.py"), default_timeout=60)
    screen.session_state["answer"] = agent.ask("q", FakeModel(evil), db)
    screen.run()
    assert not screen.exception
    assert not any("evil.example" in m.value for m in screen.markdown)


def test_nobody_orders_before_signing_up(db):
    _, rows = warehouse.run("SELECT COUNT(*) FROM analytics.fct_sales f JOIN analytics.dim_customer c USING (customer_id) "
                            "WHERE f.order_date < c.signup_date", db)
    assert rows == [(0,)]


def test_headline_numbers(db):
    data = overview.headline(db)
    assert data["month"].isoformat() == "2026-09-01"
    values = {m["name"]: m for m in data["metrics"]}
    assert values["retail_orders"]["value"] > 1000 and values["net_revenue"]["vs_year_ago"] is not None
    assert 20 < values["gross_margin_pct"]["value"] < 75 and 70 < values["wholesale_fill_rate_pct"]["value"] <= 100
