import re
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
    # in dependency order: some marts are built from other marts
    marts = ["dim_store", "dim_product", "dim_customer", "dim_account", "fct_sales", "fct_wholesale", "fct_channel_sales",
             "fct_inventory", "fct_marketing"]
    for name in marts:
        sql = (root / "marts" / f"{name}.sql").read_text()
        sql = re.sub(r"\{\{ ref\('stg_(\w+)'\) \}\}", r"raw.\1", sql)
        sql = re.sub(r"\{\{ ref\('(\w+)'\) \}\}", r"analytics.\1", sql)
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
