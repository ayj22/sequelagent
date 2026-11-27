import re

import pytest

from analyst import guardrails, seed, warehouse

FULL_NAME = re.compile(rf"\b({'|'.join(seed.FIRST)}) ({'|'.join(seed.LAST)})\b")      # how the seeded customers are named

SAFE = [
    "SELECT channel, SUM(net_revenue) FROM analytics.fct_sales GROUP BY 1",
    "WITH m AS (SELECT date_trunc('month', order_date) AS m, SUM(net_revenue) r FROM analytics.fct_sales GROUP BY 1) SELECT * FROM m ORDER BY 1",
    "SELECT segment, COUNT(*) FROM analytics.dim_customer GROUP BY segment",
    "SELECT * FROM analytics.dim_store",
    "SELECT * FROM analytics.dim_customer",
    "SELECT region FROM analytics.dim_store UNION SELECT category FROM analytics.dim_product",
]
UNSAFE = [
    "DELETE FROM analytics.fct_sales",
    "DROP TABLE analytics.dim_customer",
    "SELECT 1; DROP TABLE analytics.dim_store",
    "UPDATE analytics.dim_product SET list_price = 0",
    "COPY analytics.dim_store TO 'out.csv'",
    "ATTACH 'x.db'",
    "SET enable_external_access = true",
    "PRAGMA database_list",
    "SELECT * FROM raw.customers",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM '/etc/passwd'",
    "SELECT * FROM information_schema.tables",
    "SELECT getenv('HOME')",
    "SELECT json_execute_serialized_sql('x')",
    "SELECT nextval('s')",
    "SELECT repeat('a', 1000000000)",
    "SELECT lpad('a', 1000000000, 'b')",
    "SELECT range(1000000000)",
    "SELECT some_unknown_function(1)",
    "SELECT '/etc/passwd'.read_text()",
    "SELECT * FROM glob('*')",
    "SELECT email FROM analytics.dim_customer",
    "SELECT c.full_name FROM analytics.dim_customer c",
    # a CTE declared somewhere else must not excuse a name the database would resolve to its own catalog
    "SELECT name FROM sqlite_master WHERE (SELECT x FROM (WITH sqlite_master AS (SELECT 1 AS x) SELECT x FROM sqlite_master)) = 1",
    "WITH sqlite_master AS (SELECT * FROM sqlite_master) SELECT name FROM sqlite_master",
    "WITH a AS (SELECT * FROM sqlite_master), sqlite_master AS (SELECT 1 AS name) SELECT * FROM a",
    "SELECT (WITH duckdb_tables AS (SELECT 1 AS x) SELECT x FROM duckdb_tables) AS x, t.* FROM duckdb_tables t",
    "WITH RECURSIVE sqlite_master AS (SELECT name FROM sqlite_master UNION ALL SELECT 'x' WHERE false) SELECT * FROM sqlite_master",
    'WITH "other" AS (SELECT 1) SELECT * FROM "sqlite_master"',
    "SELECT * FROM (SHOW TABLES)",
    "SELECT * FROM (DESCRIBE analytics.dim_store)",
    "SELECT * FROM (SUMMARIZE analytics.dim_store)",
]


@pytest.mark.parametrize("sql", SAFE)
def test_read_queries_run(sql, db):
    columns, rows = warehouse.run(guardrails.check(sql), db)
    assert columns and rows


@pytest.mark.parametrize("sql", UNSAFE)
def test_unsafe_queries_never_reach_the_database(sql):
    with pytest.raises((guardrails.Blocked, guardrails.Invalid)):
        guardrails.check(sql)


@pytest.mark.parametrize("sql", [
    "WITH a AS (SELECT region FROM analytics.dim_store), b AS (SELECT * FROM a) SELECT * FROM b",
    "WITH a AS (SELECT region FROM analytics.dim_store) SELECT * FROM (SELECT * FROM a) AS inner_query",
    "WITH a AS (SELECT region FROM analytics.dim_store) SELECT * FROM a UNION SELECT * FROM a",
    "SELECT * FROM (WITH a AS (SELECT region FROM analytics.dim_store) SELECT * FROM a) AS q",
    "WITH a AS (SELECT region FROM analytics.dim_store) SELECT (SELECT COUNT(*) FROM a) AS n",
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 3) SELECT * FROM n",
])
def test_ordinary_ctes_still_work(sql, db):
    columns, rows = warehouse.run(guardrails.check(sql), db)
    assert columns and rows


@pytest.mark.parametrize("sql, expected", [
    ("SELECT 'inf'::DOUBLE AS x", None),
    ("SELECT '-inf'::DOUBLE AS x", None),
    ("SELECT 'nan'::DOUBLE AS x", None),
])
def test_numbers_that_cannot_be_shown_are_left_empty(sql, expected, db):
    assert warehouse.run(guardrails.check(sql), db)[1][0][0] is expected


@pytest.mark.parametrize("sql", [
    "SELECT list(product_name) AS x FROM analytics.dim_product CROSS JOIN analytics.dim_store",
    "SELECT {'names': list(product_name)} AS x FROM analytics.dim_product CROSS JOIN analytics.dim_store",
])
def test_nested_values_are_cut_off_too(sql, db):
    value = warehouse.run(sql, db)[1][0][0]
    assert isinstance(value, str) and len(value) == warehouse.MAX_CELL


def test_unknown_table_can_be_repaired():
    with pytest.raises(guardrails.Invalid):
        guardrails.check("SELECT * FROM analytics.sales")


def test_row_limit_is_added(db):
    _, rows = warehouse.run(guardrails.check("SELECT order_item_id FROM analytics.fct_sales"), db)
    assert len(rows) == 500


@pytest.mark.parametrize("sql", ["CREATE TABLE analytics.x(a INT)", "SELECT * FROM read_csv('/etc/passwd')", "SET enable_external_access=true"])
def test_database_itself_refuses_even_without_the_checks(sql, db):
    with pytest.raises(warehouse.QueryError):
        warehouse.run(sql, db)


def test_slow_query_is_interrupted(db):
    with pytest.raises(warehouse.QueryError):
        warehouse.run("SELECT COUNT(*) FROM range(100000000) a, range(100000) b WHERE a.range + b.range = -1", db, timeout_s=0.3)


# ways of reading a column without naming it: harmless only because the data is not there
SNEAKY = [
    "SELECT * FROM analytics.dim_customer",
    "SELECT c FROM analytics.dim_customer c",
    "SELECT CAST(c AS VARCHAR) FROM analytics.dim_customer AS c",
    "SELECT * FROM analytics.dim_customer AS t(a, b, c, d, e)",
    "SELECT COLUMNS('.*') FROM analytics.dim_customer",
    "WITH x AS (SELECT * FROM analytics.dim_customer) SELECT * FROM x",
]


@pytest.mark.parametrize("sql", SNEAKY)
def test_personal_data_cannot_be_reached_by_any_route(sql, db):
    _, rows = warehouse.run(guardrails.check(sql), db)
    text = str(rows)
    assert "@example.com" not in text and not FULL_NAME.search(text)


def test_serving_database_holds_only_published_data(db):
    _, schemas = warehouse.run("SELECT DISTINCT table_schema FROM information_schema.tables", db)
    assert schemas == [("analytics",)]
    _, columns = warehouse.run("SELECT column_name FROM information_schema.columns", db)
    assert not {"email", "full_name"} & {c[0] for c in columns}


def test_very_long_text_is_cut_off(db):
    _, rows = warehouse.run("SELECT array_to_string(list_value(product_name, product_name), repeat('x', 5000)) FROM analytics.dim_product LIMIT 1", db)
    assert len(rows[0][0]) == warehouse.MAX_CELL
