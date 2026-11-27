"""Copy the published tables, and nothing else, into the database the agent is allowed to open."""
from __future__ import annotations

from pathlib import Path

import duckdb

from analyst.config import DB_PATH, SCHEMA, WAREHOUSE_PATH
from analyst.semantic import layer


def publish(warehouse=WAREHOUSE_PATH, serving=DB_PATH) -> list[str]:
    serving = Path(serving)
    serving.parent.mkdir(parents=True, exist_ok=True)
    serving.unlink(missing_ok=True)
    con = duckdb.connect(str(serving))
    try:
        source = Path(warehouse).as_posix().replace("'", "''")
        con.execute(f"ATTACH '{source}' AS source (READ_ONLY)")
        con.execute(f"CREATE SCHEMA {SCHEMA}")
        for table, spec in layer()["tables"].items():
            columns = ", ".join(spec["columns"])          # only documented columns leave the warehouse
            con.execute(f"CREATE TABLE {SCHEMA}.{table} AS SELECT {columns} FROM source.{SCHEMA}.{table}")  # names from the repo's yaml  # nosec B608
    finally:
        con.close()
    return list(layer()["tables"])


if __name__ == "__main__":
    print("published:", ", ".join(publish()))
