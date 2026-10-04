"""Run a validated SELECT on the read-only pool and return JSON-safe results."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg import sql as pgsql
from psycopg_pool import ConnectionPool

from app.sql.validator import MAX_ROWS, validate_sql


@dataclass
class SqlResult:
    ok: bool
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_select(pool: ConnectionPool, sql: str, *, max_rows: int = MAX_ROWS,
               timeout: str = "5s") -> SqlResult:
    check = validate_sql(sql, max_rows)
    if not check.ok:
        return SqlResult(ok=False, error=f"Rejected: {check.error}")  # never touches the database
    try:
        with pool.connection() as conn, conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(pgsql.SQL("SET LOCAL statement_timeout = {}").format(pgsql.Literal(timeout)))
            cur = conn.execute(check.sql)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = [[_jsonable(v) for v in row] for row in cur.fetchmany(max_rows)]
    except psycopg.errors.QueryCanceled:
        return SqlResult(ok=False, sql=check.sql,
                         error=f"Query timed out after {timeout}. "
                               "Add filters or aggregate to make it faster.")
    except psycopg.Error as e:
        message = (e.diag.message_primary if e.diag else None) or str(e)
        return SqlResult(ok=False, sql=check.sql, error=f"Database error: {message}")
    return SqlResult(ok=True, sql=check.sql, columns=columns, rows=rows, row_count=len(rows))
