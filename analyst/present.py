"""Pick a chart and write a one-line answer from the result itself, so the explanation can never contradict the numbers."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def _is_number(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _numeric_columns(columns, rows) -> list[int]:
    return [i for i, name in enumerate(columns)
            if not name.lower().endswith(("_id", "year", "month", "quarter"))
            and any(r[i] is not None for r in rows) and all(r[i] is None or _is_number(r[i]) for r in rows)]


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


def _show(v) -> str:
    if v is None:
        return "no value"
    if isinstance(v, datetime):
        return v.date().isoformat()
    if _is_number(v):
        return f"{v:,.0f}" if float(v) == int(v) else f"{v:,.2f}"
    return str(v)


def summarize(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "No rows matched the question."
    title = lambda c: c.replace("_", " ")
    if len(rows) == 1:
        return "; ".join(f"{title(c)}: {_show(v)}" for c, v in zip(columns, rows[0])) + "."
    chart = chart_for(columns, rows)
    if chart["type"] in ("bar", "line"):
        x, y = columns.index(chart["x"]), columns.index(chart["y"])
        values = [r for r in rows if r[y] is not None]
        if values:
            top, low = max(values, key=lambda r: r[y]), min(values, key=lambda r: r[y])
            return (f"{len(rows)} results. Highest {title(columns[y])}: {_show(top[x])} ({_show(top[y])}). "
                    f"Lowest: {_show(low[x])} ({_show(low[y])}).")
    return f"{len(rows)} rows. First: " + ", ".join(_show(v) for v in rows[0]) + "."
