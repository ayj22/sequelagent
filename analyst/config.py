import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# the build warehouse holds raw data; the agent only ever opens the serving copy, which holds the published tables
WAREHOUSE_PATH = Path(os.environ.get("QUERYSHERPA_WAREHOUSE", ROOT / "data" / "warehouse.duckdb"))
DB_PATH = Path(os.environ.get("QUERYSHERPA_DB", ROOT / "data" / "serving.duckdb"))
SEMANTIC_PATH = ROOT / "semantic" / "metrics.yaml"
SCHEMA = "analytics"
ROW_LIMIT = 500
TIMEOUT_S = 15.0
MAX_REPAIRS = 2


def load_env() -> None:
    """Read KEY=value lines from .env without overriding variables that are already set."""
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#") and value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def model_name() -> str:
    return os.environ.get("QUERYSHERPA_MODEL", "gpt-6-luna")
