"""Pick a chart and write a one-line answer from the result itself, so the explanation can never contradict the numbers."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

import sqlglot
from sqlglot import exp


def _is_number(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _numeric_columns(columns, rows) -> list[int]:
    return [i for i, name in enumerate(columns)
            if not name.lower().endswith(("_id", "year", "month", "quarter"))
            and any(r[i] is not None for r in rows) and all(r[i] is None or _is_number(r[i]) for r in rows)]


def column_kind(name: str) -> str:
    """"money", "percent", "ratio", "date" or "plain": how a column should be displayed, judged from its name."""
    n = name.lower()
    if n.endswith(("_id", "year", "quarter")):
        return "plain"
    if n.endswith(("month", "date", "week_start", "_week")):
        return "date"
    if re.search(r"pct|percent|share|(return|discount|margin|fill|on_time|customer)_rate|sell_through(_rate)?$", n):
        return "percent"
    if "roas" in n or "ratio" in n:
        return "ratio"
    if re.search(r"orders?_?count|num_|count|units|pairs|customers|stores|quantity|combinations", n):
        return "plain"
    if re.search(r"revenue|margin|spend|value|price|msrp|cost|sales|discount_amount|aov|amount", n):
        return "money"
    return "plain"


def label(name: str) -> str:
    words = name.replace("_", " ").strip()
    words = re.sub(r"\bpct\b", "%", words)
    words = re.sub(r"\b(roas|aov|bopis)\b", lambda m: m.group(1).upper(), words)
    return words[:1].upper() + words[1:]


def show(value, column: str = "") -> str:
    """A value as a person would write it: $207,946, 49.2%, 3.15x, Sep 2026."""
    if value is None or value != value:          # NaN is how a data frame hands back an empty cell
        return "–"
    kind = column_kind(column)
    if isinstance(value, str) and kind == "date":
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    if isinstance(value, (date, datetime)):
        return value.strftime("%b %Y") if value.day == 1 else value.strftime("%b %-d, %Y")
    if not _is_number(value):
        return str(value)
    number = float(value)
    if kind == "money":
        return f"${number:,.0f}" if abs(number) >= 1000 else f"${number:,.2f}"
    if kind == "percent":
        return f"{number:,.1f}%"
    if kind == "ratio":
        return f"{number:,.2f}x"
    if column.lower().endswith(("_id", "year")):          # identifiers and years take no thousands separator
        return f"{number:.0f}"
    return f"{number:,.0f}" if number == int(number) else f"{number:,.2f}"


def spreadsheet_safe(value):
    """Text that a spreadsheet would run as a formula is prefixed so it is shown as text (CSV injection)."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _size_key(value) -> tuple:
    """Shoe sizes in the order a person expects: kids' C sizes, then Y sizes, then adult sizes, each by number."""
    found = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([CY]?)\s*", str(value), re.I)
    if not found:
        return (3, 0.0, str(value))
    return ({"C": 0, "Y": 1, "": 2}[found.group(2).upper()], float(found.group(1)), "")


def in_size_order(columns: list[str], rows: list, sql: str) -> list:
    """Sizes are text, so a query that sorts by size puts 10 before 8. Rows are re-ordered only when the query sorted by size
    (ascending) or did not sort at all; a ranking by anything else is left as the query returned it."""
    at = next((i for i, name in enumerate(columns) if name.lower() in ("size", "shoe_size")), None)
    if at is None:
        return rows
    order = sqlglot.parse_one(sql, read="duckdb").args.get("order")
    if order is not None:
        first = order.expressions[0]
        key = first.this
        by_position = isinstance(key, exp.Literal) and not key.is_string and key.this == str(at + 1)
        by_name = isinstance(key, exp.Column) and key.name.lower() == columns[at].lower()
        if first.args.get("desc") or not (by_position or by_name):
            return rows
    return sorted(rows, key=lambda r: _size_key(r[at]))


def chart_for(columns: list[str], rows: list[tuple]) -> dict:
    """{"type": "metric" | "line" | "bar" | "table", "x": column, "y": column}"""
    if not rows:
        return {"type": "table"}
    numbers = _numeric_columns(columns, rows)
    if len(rows) == 1 and len(columns) == 1:
        return {"type": "metric", "y": columns[0]}
    labels = [i for i in range(len(columns)) if i not in numbers]
    if not numbers or len(labels) != 1 or len(rows) < 2:
        return {"type": "table"}
    x, y = labels[0], numbers[0]
    if isinstance(rows[0][x], (date, datetime)) or columns[x].lower().endswith(("month", "date", "week_start", "quarter")):
        return {"type": "line", "x": columns[x], "y": columns[y]}
    return {"type": "bar", "x": columns[x], "y": columns[y]} if len(rows) <= 30 else {"type": "table"}


def summarize(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "No rows matched the question."
    if len(rows) == 1:
        return "; ".join(f"{label(c)}: {show(v, c)}" for c, v in zip(columns, rows[0])) + "."
    chart = chart_for(columns, rows)
    if chart["type"] in ("bar", "line"):
        x, y = columns.index(chart["x"]), columns.index(chart["y"])
        values = [r for r in rows if r[y] is not None]
        if values:
            top, low = max(values, key=lambda r: r[y]), min(values, key=lambda r: r[y])
            name = label(columns[y])
            prefix = "size " if columns[x].lower() in ("size", "shoe_size") else ""          # "size 10", not a bare "10"
            return (f"{name} is highest for {prefix}{show(top[x], columns[x])} at {show(top[y], columns[y])} "
                    f"and lowest for {prefix}{show(low[x], columns[x])} at {show(low[y], columns[y])}.")
    return f"{len(rows)} rows. First: " + ", ".join(show(v, c) for c, v in zip(columns, rows[0])) + "."
