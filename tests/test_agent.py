import json

import httpx
import pytest
from fastapi.testclient import TestClient

from analyst import agent, api, present, warehouse
from analyst.evaluate import same_result
from analyst.llm import ModelError, OpenAIModel, ReplayModel
from conftest import FakeModel

GOOD = "```sql\nSELECT channel, ROUND(SUM(net_revenue), 2) AS net_revenue FROM analytics.fct_sales GROUP BY 1 ORDER BY 2 DESC\n```"


def test_answers_with_chart_and_summary(db):
    a = agent.ask("Net revenue by channel", FakeModel(GOOD), db)
    assert a.status == "answered" and len(a.rows) == 3
    assert a.chart == {"type": "bar", "x": "channel", "y": "net_revenue"}
    assert "Highest net revenue: store" in a.message


def test_repairs_a_broken_query(db):
    model = FakeModel("```sql\nSELECT nope FROM analytics.fct_sales\n```", GOOD)
    a = agent.ask("Net revenue by channel", model, db)
    assert a.status == "answered" and a.attempts == 2 and a.input_tokens == 20
    assert "failed" in model.seen[1][-1]["content"]


def test_unsafe_query_is_blocked_without_a_retry(db):
    model = FakeModel("```sql\nDELETE FROM analytics.fct_sales\n```", GOOD)
    a = agent.ask("remove it", model, db)
    assert a.status == "blocked" and a.attempts == 1


def test_model_can_refuse(db):
    a = agent.ask("weather?", FakeModel("CANNOT_ANSWER: there is no weather data"), db)
    assert (a.status, a.message) == ("refused", "there is no weather data")


def test_gives_up_after_repairs(db):
    bad = "```sql\nSELECT nope FROM analytics.fct_sales\n```"
    assert agent.ask("q", FakeModel(bad, bad, bad), db).status == "failed"


def test_empty_and_oversized_questions_never_call_the_model(db):
    for q in ("", "x" * 600):
        assert agent.ask(q, FakeModel(), db).status == "failed"


def test_charts():
    assert present.chart_for(["total"], [(5,)])["type"] == "metric"
    assert present.chart_for(["order_month", "revenue"], [("a", 1), ("b", 2)])["type"] == "line"
    assert present.summarize(["x"], []) == "No rows matched the question."


def test_result_comparison():
    expected = [("a", 1.0), ("b", 2.0)]
    assert same_result([("B", "extra", 2.0), ("a", "extra", 1.04)], expected)
    assert not same_result([("a", 1.0), ("b", 3.0)], expected)
    assert not same_result([("a", 2.0), ("b", 1.0)], expected)          # values must stay on their rows
    assert not same_result(expected[::-1], expected, ordered=True)
    assert not same_result(expected[:1], expected)


def test_openai_client_records_and_replays(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

    monkeypatch.setattr("analyst.llm.time.sleep", lambda s: None)
    path = tmp_path / "r.json"
    model = OpenAIModel("m", record_to=path, client=httpx.Client(transport=httpx.MockTransport(handler)))
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    assert model.complete(messages).text == "hi" and len(calls) == 2
    assert "test-key" not in path.read_text()
    assert ReplayModel(path).complete([{"role": "system", "content": "changed"}, messages[1]]).input_tokens == 3
    with pytest.raises(ModelError):
        ReplayModel(path).complete([{"role": "user", "content": "other"}])


def test_api(db, monkeypatch):
    monkeypatch.setattr(warehouse, "DB_PATH", db)
    api.app.dependency_overrides[api.get_model] = lambda: FakeModel(GOOD)
    try:
        client = TestClient(api.app)
        body = client.post("/ask", json={"question": "Net revenue by channel"}).json()
        assert body["status"] == "answered" and body["sql"].startswith("SELECT")
        assert client.post("/ask", json={"question": ""}).status_code == 422
        assert "net_revenue" in client.get("/metrics").json()
    finally:
        api.app.dependency_overrides.clear()


def test_every_golden_query_runs(db):
    import yaml
    from analyst.evaluate import EVALS
    for case in yaml.safe_load((EVALS / "golden.yaml").read_text()):
        _, rows = warehouse.run(case["sql"], db)
        assert rows and rows[0][0] is not None, case["id"]


def test_safety_grading():
    from analyst.evaluate import is_safe
    answered = agent.Answer(question="q", status="answered", rows=[[1, "TN"]])
    assert is_safe({}, agent.Answer(question="q", status="blocked"))
    assert not is_safe({}, answered)
    assert is_safe({"may_answer_without": "@example"}, answered)
    leaked = agent.Answer(question="q", status="answered", rows=[["a@example.com"]])
    assert not is_safe({"may_answer_without": "@example"}, leaked)
