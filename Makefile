PY := .venv/bin/python
export DBT_SEND_ANONYMOUS_USAGE_STATS := false

.PHONY: setup data test eval replay app api demo
setup:            ## create the virtual environment and install everything
	python3 -m venv .venv && $(PY) -m pip install -q -r requirements-dev.txt
data:             ## synthetic data -> dbt models and tests -> serving database
	$(PY) -m analyst.seed
	cd dbt && ../.venv/bin/dbt build --profiles-dir .
	$(PY) -m analyst.publish
test:
	$(PY) -m pytest -q
eval:             ## live evaluation (needs OPENAI_API_KEY, makes ~40 model calls)
	$(PY) -m analyst.evaluate
replay:           ## re-score the recorded replies: free and deterministic
	$(PY) -m analyst.evaluate --replay --min-accuracy 90
app:
	.venv/bin/streamlit run analyst/app.py
api:
	.venv/bin/uvicorn analyst.api:app --reload
demo:             ## regenerate the README screenshots (needs OPENAI_API_KEY and Google Chrome)
	$(PY) scripts/record_demo.py
