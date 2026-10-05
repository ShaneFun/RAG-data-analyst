"""Pick a simple chart for a query result (the front end draws it)."""
import re

_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def chart_hint(columns: list[str], rows: list[list]) -> dict:
    """line: first column is a date and a numeric column exists.
    bar: first column is text, at most 20 rows, and a numeric column exists.
    none: anything else, including a first column with repeated values (e.g. one row per
    month AND supplier), where a single line or bar series would be misleading."""
    none = {"type": "none", "x": None, "y": None}
    if len(columns) < 2 or not rows:
        return none
    if len({r[0] for r in rows}) != len(rows):
        return none
    numeric = [i for i in range(1, len(columns)) if all(_is_number(r[i]) for r in rows)]
    if not numeric:
        return none
    first = [r[0] for r in rows]
    x, y = columns[0], columns[numeric[0]]
    if all(isinstance(v, str) and _DATE.match(v) for v in first):
        return {"type": "line", "x": x, "y": y}
    if all(isinstance(v, str) for v in first) and len(rows) <= 20:
        return {"type": "bar", "x": x, "y": y}
    return none
