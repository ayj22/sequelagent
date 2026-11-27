"""Turn the semantic layer into the instructions the model sees, and the lists the guardrails enforce."""
from __future__ import annotations

from functools import lru_cache

import yaml

from analyst.config import SCHEMA, SEMANTIC_PATH


@lru_cache(maxsize=1)
def layer() -> dict:
    return yaml.safe_load(SEMANTIC_PATH.read_text())


def allowed_tables() -> set[str]:
    return set(layer()["tables"])


def pii_columns() -> set[str]:
    return {c.lower() for c in layer()["pii_columns"]}


def system_prompt() -> str:
    d = layer()
    lines = [f"You are a careful analytics engineer. Write one DuckDB SQL query that answers a question about {d['business']}.",
             "", d["data_range"], "", f"Tables (always write them as {SCHEMA}.<table>):"]
    for name, t in d["tables"].items():
        lines.append(f"- {SCHEMA}.{name} ({t['grain']})")
        lines += [f"    {col}: {desc}" for col, desc in t["columns"].items()]
    lines += ["", "Metric definitions (use them exactly):"] + [f"- {k} = {v}" for k, v in d["metrics"].items()]
    lines += ["", "Rules:"] + [f"- {r}" for r in d["rules"]]
    lines += ["- Never select personal data: " + ", ".join(d["pii_columns"]) + ".", "- Read only: a single SELECT (CTEs are fine)."]
    for ex in d["examples"]:
        lines += ["", f"Example question: {ex['question']}", "```sql", ex["sql"].strip(), "```"]
    lines += ["", "Reply with only the query in a ```sql block.",
              "If the question cannot be answered from these tables, asks to change data, or asks for personal data, reply with exactly:",
              "CANNOT_ANSWER: <one short reason>"]
    return "\n".join(lines)
