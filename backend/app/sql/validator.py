"""SQL validator: only a single, read-only SELECT over allowed tables gets through."""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

ALLOWED_TABLES = frozenset({"customers_safe", "products", "orders", "order_items", "refunds"})
MAX_ROWS = 200
_QUERY_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
    "TruncateTable", "Copy", "Grant", "Revoke", "Command", "Into", "Set", "Lock",
)
_FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NODE_NAMES if hasattr(exp, n))
_FORBIDDEN_FUNCTIONS = frozenset({
    "set_config", "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_terminate_backend",
    "pg_cancel_backend", "pg_reload_conf", "pg_read_file", "pg_read_binary_file",
    "pg_ls_dir", "lo_import", "lo_export", "dblink", "dblink_exec",
})


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    sql: str | None = None    # the (possibly LIMIT-adjusted) SQL to execute
    error: str | None = None


def _reject(reason: str) -> ValidationResult:
    return ValidationResult(ok=False, error=reason)


def validate_sql(sql: str, max_rows: int = MAX_ROWS) -> ValidationResult:
    if not sql or not sql.strip():
        return _reject("Empty query.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        return _reject(f"Could not parse SQL: {str(e).splitlines()[0]}")
    if len(statements) != 1:
        return _reject("Exactly one SQL statement is allowed.")
    tree = statements[0]

    if not isinstance(tree, _QUERY_ROOTS):
        return _reject("Only SELECT queries are allowed.")
    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            return _reject(f"Forbidden operation: {type(node).__name__}.")
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name in _FORBIDDEN_FUNCTIONS:
                return _reject(f"Function not allowed: {name}.")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        schema = (table.db or "").lower()
        if not name:
            return _reject("Table functions are not allowed in FROM.")
        if name in cte_names and not schema:
            continue
        if schema not in ("", "public") or name not in ALLOWED_TABLES:
            return _reject(f"Table not allowed: {table.sql(dialect='postgres')}. "
                           f"Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}.")

    limit = tree.args.get("limit")
    current = None
    if limit is not None and isinstance(limit.expression, exp.Literal) and limit.expression.is_int:
        current = int(limit.expression.this)
    if current is None or current > max_rows:
        if isinstance(tree, exp.Select):
            tree = tree.limit(max_rows)
        else:  # set operation: wrap so the LIMIT applies to the whole result
            tree = exp.select("*").from_(tree.subquery("q")).limit(max_rows)
    return ValidationResult(ok=True, sql=tree.sql(dialect="postgres"))
