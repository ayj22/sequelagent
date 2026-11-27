# 🛡️ SequelAgent: Governed AI Analyst Agent

**Ask a business question in plain English and get a checked answer. SequelAgent writes the SQL, makes sure it is safe,
runs it read-only, and shows you the chart, the explanation and the query behind it.**

[![ci](https://github.com/ayj22/sequelagent/actions/workflows/ci.yml/badge.svg)](https://github.com/ayj22/sequelagent/actions/workflows/ci.yml)

![SequelAgent demo: typed questions answered with charts and SQL, and a destructive request refused](docs/demo.gif)

*A one-minute walkthrough, recorded from the running app with live model calls.*

## What "governed" means here

An AI model can write a query that is wrong or harmful, so the agent works inside fixed rules:

| Rule | What it means for you |
|---|---|
| Shared metric definitions | The model is given one definition of each metric, such as net revenue or margin |
| Checked before it runs | Only a single read query on approved tables is allowed |
| Read-only data | The agent cannot change or delete anything |
| No personal data | The database it queries holds only the published columns, without customer names or email addresses |
| Open answers | Every answer shows its SQL |
| Measured | A scorecard reports correct answers and how unsafe requests were handled |

When a query fails, the agent reads the error and tries to repair it.

## Why it exists

Most text-to-SQL demos stop at "the model wrote a query". SequelAgent is built around the parts that decide whether such a tool
can be used at work: shared metric definitions, treating the model as untrusted, and measuring accuracy and safety on every change.

| | Latest run (`gpt-6-luna`) |
|---|---|
| Correct answers | 30 of 30 |
| Unsafe or unanswerable requests handled safely | 10 of 10 |
| Median time per question | 1.7 s |
| Tokens per question | about 1,060 in, 140 out |

Read [what these numbers do and don't mean](#evaluation) before quoting them. Full results: [SCORECARD.md](evals/results/SCORECARD.md).

## Demo

**Start here**: the latest month at a glance, then type a question or pick an example.

![Business overview with headline numbers, a question box and example questions](docs/home.png)

| Question | What you get |
|---|---|
| *What was net revenue by region last quarter?* | ![Bar chart of net revenue by region](docs/region.png) |
| *Show monthly net revenue in 2026* | ![Line chart of monthly net revenue](docs/monthly.png) |
| *Which 5 brands had the highest gross margin percentage this year?* | ![Bar chart of brand gross margin](docs/margin.png) |
| *Delete all orders from 2025* | ![The request is refused](docs/blocked.png) |

**Nothing is a black box**: every answer carries the query that produced it.

![The SQL behind an answer](docs/sql.png)

What the app does for the person asking:

- shows progress while it works: writing the query, checking it, running it
- writes values the way people read them ($207,946, 49.2%, Sep 2026)
- says plainly why a request was not answered and what to try instead
- offers the result as a table and a CSV download

`make demo` re-records the walkthrough.

## How it works

```mermaid
flowchart LR
    Q[Question] --> M[Model]
    S[Semantic layer<br/>tables, metrics, rules] --> M
    M -->|cannot answer| R[Refuse, with reason]
    M -->|SQL| G{Guardrails<br/>parse the SQL}
    G -->|unsafe| B[Block, no retry]
    G -->|ok| D[(Serving database<br/>read-only, locked)]
    D -->|error| M
    D --> A[Answer, chart, SQL]

    subgraph Build
      RAW[(Synthetic raw data)] --> DBT[dbt models + tests] --> PUB[Publish documented columns only]
    end
    PUB --> D
```

- **Data**: Cedar Ridge Outfitters, an **invented** outdoor and apparel retailer: 24 stores, 172 products, 8 brands, 24,000
  customers, about 146,000 orders and 277,000 order lines from January 2025 to September 2026, plus monthly inventory and weekly
  marketing spend. It behaves like a real business (holiday and back-to-school peaks, weekend traffic, seasonal products, a
  growing online share, higher online returns, loyalty customers who buy more). Sales, products and customers are made up;
  the place names are real. It is generated from a fixed seed.
- **Modeling**: dbt on DuckDB, with uniqueness, not-null, relationship and accepted-value tests.
- **Semantic layer**: [`semantic/metrics.yaml`](semantic/metrics.yaml) is the single definition of each metric ("revenue" means
  net revenue; stock is a snapshot and is never summed across months). The prompt is generated from it.
- **Repair**: a query that fails to run goes back to the model with the error, at most twice. An unsafe query is never retried.
- **Explanations**: the one-line answer and the chart are computed from the result rows, not written by the model, so they cannot
  disagree with the numbers.

## Safety

The model is treated as untrusted. Four independent layers stand between its output and the data:

1. **Data minimisation**: names and emails are never copied into the database the app opens. Renaming columns, `SELECT *` or
   whole-row tricks find nothing, because the data is not there.
2. **SQL checks** ([`guardrails.py`](analyst/guardrails.py)): the query is parsed into a syntax tree. Only one `SELECT` over listed
   tables is allowed; writes, settings changes, table functions, file and system functions and personal column names are refused.
3. **Locked database**: read-only connection, no file or network access, settings locked, memory limit.
4. **Limits**: 500 rows, 2,000 characters per value, 15 seconds, 500-character questions, two repair attempts, and a cap on
   how many questions can be asked per minute.

Around the model:

- Text written by the model is shown as plain text, so it cannot place links or images on the screen.
- CSV downloads neutralise spreadsheet formulas.
- Provider error messages are never shown or logged, and the key is sent only over HTTPS.
- The API accepts an optional shared token (`SEQUELAGENT_API_TOKEN`).
- CI scans the whole git history for secrets, audits dependencies for known vulnerabilities and runs a static code scan, on
  every push and weekly. Details: [SECURITY.md](SECURITY.md).

In live runs the model usually refuses bad requests itself, so layers 2 to 4 are tested directly, with hostile SQL that bypasses
the model ([`tests/test_guardrails.py`](tests/test_guardrails.py)).

## Evaluation

```bash
make eval     # live: calls the model, rewrites the scorecard
make replay   # free: re-scores the recorded replies
```

- **30 questions** ([`golden.yaml`](evals/golden.yaml)), each with a hand-written reference query the model never sees. A question
  passes when the agent's result rows match the reference rows (column names and extra columns ignored; small rounding allowed;
  order checked only for rankings).
- **10 hostile or unanswerable requests** ([`adversarial.yaml`](evals/adversarial.yaml)): destructive commands, requests for
  personal data, prompt injection, file access, questions the data cannot answer.
- **CI** builds the data, runs the dbt tests and unit tests, replays the recorded replies and fails below 90% accuracy or on any
  unsafe answer, then builds and health-checks the Docker image.

### What the numbers do and don't mean

Results from the live runs made while building:

| Run | Correct | Safe | Notes |
|---|---|---|---|
| 1 | 29 of 30 | 10 of 10 | Miss: "revenue by region" included online orders, which have no region, as an extra empty row |
| 2 | 30 of 30 | 9 of 10 | The model ran an injected `SELECT *` on the customer table. The result held no personal data (layer 1) |
| 3 | 30 of 30 | 10 of 10 | |
| 4 | 30 of 30 | 10 of 10 | After the region rule below |
| 5 | 30 of 30 | 10 of 10 | New, larger dataset. The recorded run behind the scorecard |

- The run 1 miss happened again while recording the demo. A rule was then added to the semantic layer ("leave online orders out
  of breakdowns by region"). Run 4 therefore uses a prompt improved with knowledge of a test question.
- After run 2, that one injection case was changed to also pass when the answer contains no personal data. All other cases must
  still be refused or blocked.
- Model output varies between runs. A single 100% is not a guarantee.
- The 30 questions cover one small, well-documented schema, and the same author wrote the questions and the semantic layer.
  Expect lower accuracy on a large, messy warehouse.
- Replay in CI catches regressions in data, metrics, guardrails and scoring. It does **not** detect a change in model behaviour or
  the effect of editing the prompt; run `make eval` for that.

## Run it

Needs Python 3.12 or 3.13 and an OpenAI API key (any OpenAI-compatible endpoint works through `OPENAI_BASE_URL`).

```bash
make setup
cp .env.example .env    # add OPENAI_API_KEY
make data
make app                # http://localhost:8501
```

Other entry points:

```bash
make api                                                   # POST /ask on http://localhost:8000/docs
.venv/bin/python -m analyst.cli "Average order value by loyalty tier in 2026"
make test
make security                                              # dependency audit and code scan
```

Docker:

```bash
docker build -t sequelagent .
docker run -p 8501:8501 -e OPENAI_API_KEY sequelagent
```

AWS notes: [deploy/aws.md](deploy/aws.md) (written, not yet run against a live account).

## Layout

```
analyst/     agent, guardrails, warehouse access, model client, evaluation, API, web app
dbt/         staging views and published marts, with tests
semantic/    metric definitions and business rules
evals/       questions, hostile cases, recorded replies, scorecard
tests/       unit and safety tests (no API key needed)
scripts/     demo recorder
```

## Limitations and next steps

- No login or rate limiting: do not expose the app publicly as it is.
- Single question, no follow-ups ("now split that by channel").
- The whole schema goes into the prompt; a large warehouse would need table retrieval first.
- Next: a harder question set with ambiguous wording, model-by-model comparison, and a Snowflake adapter.
