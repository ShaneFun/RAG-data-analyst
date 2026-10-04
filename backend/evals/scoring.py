"""How an agent answer is scored against a gold answer.

Execution accuracy: run the gold SQL and the agent's SQL and compare the RESULTS, not the
SQL text (many different queries are correct). The comparison is deliberately lenient about
presentation (row order, column order, extra columns, rounding) and strict about content
(same number of rows, every gold column's values present).
"""
from __future__ import annotations

import math
import re

REL_TOL = 0.005   # 0.5% relative tolerance (rounding to 2-4 decimals)
ABS_TOL = 0.006   # absorbs rounding to 2 decimals on small numbers

DECLINE_PATTERN = re.compile(
    r"\b(can't|cannot|can not|unable|not able|won't|will not|don't have access|"
    r"not available|decline|sorry|only answer|only help)\b",
    re.IGNORECASE,
)


def _norm(value):
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00.*", text):  # timestamp at midnight -> date
        text = text[:10]
    return text


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _sort_key(value):
    return (0, value, "") if isinstance(value, float) else (1, 0.0, str(value))


def _column_equal(gold: list, pred: list) -> bool:
    gold, pred = sorted(gold, key=_sort_key), sorted(pred, key=_sort_key)
    if all(_same(g, p) for g, p in zip(gold, pred, strict=True)):
        return True
    # a rate column written as a percentage (0.0697 vs 6.97)
    return all(isinstance(g, float) and isinstance(p, float) and _same(g * 100, p)
               for g, p in zip(gold, pred, strict=True))


def _is_time_label(column: list) -> bool:
    return all(isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in column)


def _columns(rows: list[list]) -> list[list]:
    return [list(col) for col in zip(*rows, strict=True)]


def _table_match(gold_rows: list[list], pred_rows: list[list]) -> bool:
    if len(gold_rows) != len(pred_rows):
        return False
    gold_cols, pred_cols = _columns(gold_rows), _columns(pred_rows)
    # time labels ("2025-03-01" vs "2025-03" vs quarter 1) can be written many ways: the
    # row count and the measure columns still have to match
    measures = [c for c in gold_cols if not _is_time_label(c)] or gold_cols
    unused = list(range(len(pred_cols)))
    for gold in measures:
        match = next((i for i in unused if _column_equal(gold, pred_cols[i])), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def _same_or_percent(gold, value) -> bool:
    if isinstance(gold, float) and isinstance(value, float):
        return _same(gold, value) or _same(gold * 100, value)
    return gold == value


def results_match(gold_rows: list[list], pred_rows: list[list]) -> bool:
    """Is the gold answer contained in the agent's last result?

    Lenient about presentation, strict about content:
    - row and column order, extra columns, rounding (0.5%) don't matter;
    - a single gold value may appear anywhere in the result; rates may be percentages;
    - a top-N answer may list extra rows after the gold rows (e.g. top 5 for "the top 1");
    - time-label columns may be formatted differently.
    """
    if not gold_rows:
        return not pred_rows
    gold = [[_norm(v) for v in row] for row in gold_rows]
    pred = [[_norm(v) for v in row] for row in pred_rows]
    if len(gold) == 1 and len(gold[0]) == 1:
        return any(_same_or_percent(gold[0][0], v) for row in pred for v in row)
    if _table_match(gold, pred):
        return True
    return len(pred) > len(gold) and _table_match(gold, pred[:len(gold)])


def keywords_ok(answer: str, groups: list[list[str]]) -> bool:
    """Every group must have at least one keyword in the answer (case-insensitive)."""
    text = answer.lower()
    return all(any(word.lower() in text for word in group) for group in groups)


def looks_like_refusal(answer: str, sql_count: int) -> bool:
    return sql_count == 0 and bool(DECLINE_PATTERN.search(answer))


def score_item(item: dict, answer: str, sql_count: int, pred_rows: list[list],
               gold_rows: list[list] | None) -> dict:
    """Score one question. Returns {"passed": bool, "checks": {name: bool}}."""
    checks: dict[str, bool] = {}
    if item.get("expect_refusal"):
        checks["refused"] = looks_like_refusal(answer, sql_count)
    if gold_rows is not None:
        checks["result"] = results_match(gold_rows, pred_rows)
    if item.get("keywords"):
        checks["keywords"] = keywords_ok(answer, item["keywords"])
    return {"passed": bool(checks) and all(checks.values()), "checks": checks}
