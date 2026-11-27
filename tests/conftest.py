import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyst import publish, seed  # noqa: E402
from analyst.llm import Reply  # noqa: E402


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    """A warehouse with the marts built directly from the raw tables (the dbt build is checked separately in CI)."""
    folder = tmp_path_factory.mktemp("wh")
    path = folder / "warehouse.duckdb"
    seed.write(path)
    root = Path(__file__).resolve().parent.parent / "dbt" / "models"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA analytics")
    for name in ["dim_store", "dim_product", "dim_customer", "fct_sales", "fct_inventory", "fct_marketing"]:
        sql = (root / "marts" / f"{name}.sql").read_text()
        for table in ["stores", "products", "customers", "orders", "order_items", "inventory", "marketing_spend"]:
            sql = sql.replace("{{ ref('stg_" + table + "') }}", "raw." + table)
        con.execute(f"CREATE TABLE analytics.{name} AS {sql}")
    con.close()
    serving = folder / "serving.duckdb"
    publish.publish(path, serving)
    return serving


class FakeModel:
    model = "fake"

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def complete(self, messages):
        self.seen.append(list(messages))
        return Reply(self.replies.pop(0), 10, 5)
