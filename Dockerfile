FROM python:3.12-slim
WORKDIR /app
ENV DBT_SEND_ANONYMOUS_USAGE_STATS=false PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade "pip>=26.2" && pip install --no-cache-dir -r requirements.txt
COPY . .
# the synthetic warehouse is built into the image; the API key is supplied only at run time
RUN python -m analyst.seed && (cd dbt && dbt build --profiles-dir .) && python -m analyst.publish && rm data/warehouse.duckdb \
 && useradd --create-home app
# the app runs without root and cannot change its own code or data
USER app
EXPOSE 8501
CMD ["streamlit", "run", "analyst/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
