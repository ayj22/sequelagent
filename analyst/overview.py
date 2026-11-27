"""The headline numbers on the home screen: the latest complete month against the month before and a year earlier."""
from __future__ import annotations

from analyst import warehouse

SQL = """
WITH latest AS (SELECT date_trunc('month', MAX(sale_date))::DATE AS m FROM analytics.fct_channel_sales),
company AS (
    SELECT date_trunc('month', sale_date)::DATE AS month, SUM(net_revenue) AS net_revenue,
           SUM(gross_margin) / NULLIF(SUM(net_revenue), 0) * 100 AS gross_margin_pct
    FROM analytics.fct_channel_sales GROUP BY 1),
retail AS (SELECT date_trunc('month', order_date)::DATE AS month, COUNT(DISTINCT order_id) AS retail_orders
           FROM analytics.fct_sales GROUP BY 1),
wholesale AS (SELECT date_trunc('month', ship_date)::DATE AS month,
                     SUM(units_shipped) * 100.0 / NULLIF(SUM(units_ordered), 0) AS wholesale_fill_rate_pct
              FROM analytics.fct_wholesale GROUP BY 1),
months AS (SELECT * FROM company LEFT JOIN retail USING (month) LEFT JOIN wholesale USING (month))
SELECT CASE months.month WHEN latest.m THEN 'now' WHEN (latest.m - INTERVAL 1 MONTH)::DATE THEN 'previous' ELSE 'year_ago' END AS period,
       months.*
FROM months, latest
WHERE months.month IN (latest.m, (latest.m - INTERVAL 1 MONTH)::DATE, (latest.m - INTERVAL 1 YEAR)::DATE)
"""
METRICS = ["net_revenue", "gross_margin_pct", "retail_orders", "wholesale_fill_rate_pct"]


def headline(db_path=None) -> dict:
    """{"month": date, "metrics": [{"name", "value", "vs_previous", "vs_year_ago"}]}. Changes are percentages, except
    for the margin rate, which changes in percentage points."""
    columns, rows = warehouse.run(SQL, db_path)
    periods = {r[0]: dict(zip(columns[1:], r[1:])) for r in rows}
    now = periods["now"]

    def change(name: str, other: str):
        before = periods.get(other, {}).get(name)
        if before in (None, 0) or now[name] is None:
            return None
        if name.endswith("_pct"):
            return float(now[name]) - float(before)
        return (float(now[name]) / float(before) - 1) * 100

    return {"month": now["month"], "metrics": [{"name": n, "value": now[n], "vs_previous": change(n, "previous"),
                                                "vs_year_ago": change(n, "year_ago")} for n in METRICS]}
