"""question -> SQL -> safety check -> run -> (repair on error) -> answer"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field

from analyst import guardrails, present, semantic, warehouse
from analyst.config import MAX_REPAIRS

SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)
MAX_QUESTION = 500


@dataclass
class Answer:
    question: str
    status: str                      # answered | refused | blocked | failed
    message: str = ""
    sql: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    chart: dict = field(default_factory=dict)
    attempts: int = 0
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def extract_sql(text: str) -> str:
    found = SQL_BLOCK.search(text)
    return (found.group(1) if found else text).strip().rstrip(";")


def ask(question: str, model, db_path=None, max_repairs: int = MAX_REPAIRS) -> Answer:
    question = " ".join((question or "").split())
    answer = Answer(question=question, status="failed")
    if not question or len(question) > MAX_QUESTION:
        answer.message = f"Ask a question of 1 to {MAX_QUESTION} characters."
        return answer
    started = time.monotonic()
    messages = [{"role": "system", "content": semantic.system_prompt()}, {"role": "user", "content": question}]
    for attempt in range(1, max_repairs + 2):
        reply = model.complete(messages)
        answer.attempts = attempt
        answer.input_tokens += reply.input_tokens
        answer.output_tokens += reply.output_tokens
        if reply.text.strip().upper().startswith("CANNOT_ANSWER"):
            answer.status = "refused"
            answer.message = reply.text.split(":", 1)[-1].strip() or "The data cannot answer this."
            break
        answer.sql = extract_sql(reply.text)
        try:
            columns, rows = warehouse.run(guardrails.check(answer.sql), db_path)
        except guardrails.Blocked as exc:           # unsafe: refuse, do not coach the model around the rule
            answer.status, answer.message = "blocked", str(exc)
            break
        except (guardrails.Invalid, warehouse.QueryError) as exc:
            answer.message = str(exc)
            messages += [{"role": "assistant", "content": reply.text},
                         {"role": "user", "content": f"That query failed: {exc}\nReply with a corrected query in a ```sql block."}]
            continue
        answer.status, answer.columns, answer.rows = "answered", columns, [list(r) for r in rows]
        answer.chart = present.chart_for(columns, rows)
        answer.message = present.summarize(columns, rows)
        break
    answer.seconds = round(time.monotonic() - started, 2)
    return answer
