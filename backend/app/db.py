"""Connection pools. Each connection is reset when it goes back to the pool."""
import psycopg
from psycopg_pool import ConnectionPool


def _reset(conn: psycopg.Connection) -> None:
    conn.execute("RESET ALL")  # undo any session-level SET made while borrowed


def make_pool(conninfo: str, min_size: int = 1, max_size: int = 5) -> ConnectionPool:
    return ConnectionPool(
        conninfo,
        min_size=min_size,
        max_size=max_size,
        kwargs={"autocommit": True},
        reset=_reset,
        open=True,
    )
