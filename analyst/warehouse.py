"""Run a checked query on a locked-down, read-only connection with a time limit."""
from __future__ import annotations

import threading

import duckdb

from analyst.config import DB_PATH, TIMEOUT_S


MAX_CELL = 2000        # characters kept from any one text value


class QueryError(ValueError):
    """The database rejected the query or it ran too long."""


def connect(path=None) -> duckdb.DuckDBPyConnection:
    """Second line of defence behind the SQL checks: read-only, no files or network, and the settings cannot be changed."""
    path = path or DB_PATH
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `make data` first")
    return duckdb.connect(str(path), read_only=True,
                          config={"enable_external_access": False, "memory_limit": "1GB", "threads": 2, "max_temp_directory_size": "0KB",
                                  "autoinstall_known_extensions": False, "autoload_known_extensions": False, "lock_configuration": True})


def run(sql: str, path=None, timeout_s: float = TIMEOUT_S) -> tuple[list[str], list[tuple]]:
    con = connect(path)
    timer = threading.Timer(timeout_s, con.interrupt)
    try:
        timer.start()
        cursor = con.execute(sql)
        columns = [d[0] for d in cursor.description]
        return columns, [tuple(v[:MAX_CELL] if isinstance(v, str) else v for v in row) for row in cursor.fetchall()]
    except duckdb.InterruptException as exc:
        raise QueryError(f"The query ran longer than {timeout_s:.0f} seconds") from exc
    except duckdb.Error as exc:
        raise QueryError(str(exc).split("\n\n")[0][:500]) from exc
    finally:
        timer.cancel()
        con.close()
