"""The headline numbers on the home screen: the latest complete month against the month before and a year earlier."""
from __future__ import annotations

from analyst import warehouse

SQL = """
WITH latest AS (SELECT date_trunc('month', MAX(order_date))::DATE AS m FROM analytics.fct_sales),
months AS (
    SELECT date_trunc('month', order_date)::DATE AS month, SUM(net_revenue) AS net_revenue,
           SUM(gross_margin) / NULLIF(SUM(net_revenue), 0) * 100 AS gross_margin_pct,
           COUNT(DISTINCT order_id) AS orders,
           SUM(net_revenue) / NULLIF(COUNT(DISTINCT order_id), 0) AS average_order_value
    FROM analytics.fct_sales GROUP BY 1)
SELECT CASE months.month WHEN latest.m THEN 'now' WHEN (latest.m - INTERVAL 1 MONTH)::DATE THEN 'previous' ELSE 'year_ago' END AS period,
       months.*
FROM months, latest
WHERE months.month IN (latest.m, (latest.m - INTERVAL 1 MONTH)::DATE, (latest.m - INTERVAL 1 YEAR)::DATE)
"""
METRICS = ["net_revenue", "gross_margin_pct", "orders", "average_order_value"]


def headline(db_path=None) -> dict:
    """{"month": date, "metrics": [{"name", "value", "vs_previous", "vs_year_ago"}]}. Changes are percentages, except
    for the margin rate, which changes in percentage points."""
    columns, rows = warehouse.run(SQL, db_path)
    periods = {r[0]: dict(zip(columns[1:], r[1:])) for r in rows}
    now = periods["now"]

    def change(name: str, other: str):
        before = periods.get(other, {}).get(name)
        if before in (None, 0):
            return None
        if name.endswith("_pct"):
            return float(now[name]) - float(before)
        return (float(now[name]) / float(before) - 1) * 100

    return {"month": now["month"], "metrics": [{"name": n, "value": now[n], "vs_previous": change(n, "previous"),
                                                "vs_year_ago": change(n, "year_ago")} for n in METRICS]}
