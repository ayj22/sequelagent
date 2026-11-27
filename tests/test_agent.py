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
    assert "Net revenue is highest for store at $" in a.message


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


def test_the_whole_company_view_matches_retail_plus_wholesale(db):
    total = warehouse.run("SELECT SUM(net_revenue) FROM analytics.fct_channel_sales", db)[1][0][0]
    parts = warehouse.run("SELECT (SELECT SUM(net_revenue) FROM analytics.fct_sales) + "
                          "(SELECT SUM(net_revenue) FROM analytics.fct_wholesale)", db)[1][0][0]
    assert float(total) == pytest.approx(float(parts), abs=1)


def test_stock_keeps_every_retail_pair_sold_in_a_store(db):
    stocked = warehouse.run("SELECT SUM(units_sold) FROM analytics.fct_inventory", db)[1][0][0]
    sold = warehouse.run("SELECT SUM(quantity) FILTER (WHERE NOT is_returned) FROM analytics.fct_sales "
                         "WHERE store_id IS NOT NULL", db)[1][0][0]
    assert stocked == sold


@pytest.mark.parametrize("order_by, sizes", [
    ("", ["8", "10", "11"]),                          # unsorted: shoe order
    ("ORDER BY size", ["8", "10", "11"]),             # sorted as text by the database: shoe order
    ("ORDER BY 1", ["8", "10", "11"]),
    ("ORDER BY f.size ASC", ["8", "10", "11"]),
    ("ORDER BY pairs DESC", ["10", "11", "8"]),       # a ranking that happens to look like text order is kept
    ("ORDER BY 2 DESC, 1", ["10", "11", "8"]),
    ("ORDER BY size DESC", ["10", "11", "8"]),
])
def test_shoe_sizes_read_in_order_without_breaking_rankings(order_by, sizes):
    rows = [("10", 9), ("11", 5), ("8", 1)]
    ordered = present.in_size_order(["size", "pairs"], rows, f"SELECT f.size, 1 AS pairs FROM analytics.fct_sales f {order_by}")
    assert [r[0] for r in ordered] == sizes


def test_a_size_is_named_as_a_size():
    text = present.summarize(["size", "weeks_of_supply"], [("8", 13.87), ("10", 8.1)])
    assert "highest for size 8" in text and "lowest for size 10" in text


def test_childrens_sizes_come_before_youth_sizes():
    rows = [("1Y", 1), ("10C", 2), ("2Y", 3), ("13C", 4)]
    ordered = present.in_size_order(["size", "pairs"], rows, "SELECT size, 1 AS pairs FROM analytics.fct_sales")
    assert [r[0] for r in ordered] == ["10C", "13C", "1Y", "2Y"]
    assert present.in_size_order(["region", "pairs"], rows, "SELECT 1") == rows


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


@pytest.mark.parametrize("value, column, shown", [
    (207945.87, "net_revenue", "$207,946"), (84.5, "average_order_value", "$84.50"), (49.17, "gross_margin_pct", "49.2%"),
    (11.2, "return_rate_pct", "11.2%"), (3.151, "roas", "3.15x"), (1520, "units_sold", "1,520"), (2026, "order_year", "2026"),
    (812, "orders_count", "812"), (None, "net_revenue", "–"), ("2026-09-01", "order_month", "Sep 2026"), ("West", "region", "West"),
])
def test_values_are_written_the_way_people_write_them(value, column, shown):
    assert present.show(value, column) == shown


def test_progress_steps_are_reported(db):
    steps = []
    agent.ask("Net revenue by channel", FakeModel("```sql\nSELECT nope FROM analytics.fct_sales\n```", GOOD), db, on_step=steps.append)
    assert steps == ["writing", "checking", "running", "repairing", "checking", "running"]


def test_empty_cells_are_shown_as_a_dash():
    nan = float("nan")
    assert present.show(nan, "region") == "–" and present.show(nan, "net_revenue") == "–"


@pytest.mark.parametrize("sql", [
    "SELECT NULL AS region, 1.0 AS net_revenue UNION ALL SELECT 'West', 2.0",          # empty label
    "SELECT 'a' AS region, NULL::DOUBLE AS net_revenue UNION ALL SELECT 'b', 2.0",     # empty value
    "SELECT SUM(net_revenue) AS net_revenue FROM analytics.fct_sales WHERE order_date < DATE '2000-01-01'",
    "SELECT order_date, net_revenue FROM analytics.fct_sales WHERE false",
])
def test_the_screen_renders_awkward_results(sql, db, monkeypatch):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(warehouse, "DB_PATH", db)
    answer = agent.ask("q", FakeModel(f"```sql\n{sql}\n```"), db)
    assert answer.status == "answered", answer.message
    screen = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "analyst" / "app.py"), default_timeout=30)
    screen.session_state["answer"] = answer
    screen.run()
    assert not screen.exception, [e.value for e in screen.exception]
