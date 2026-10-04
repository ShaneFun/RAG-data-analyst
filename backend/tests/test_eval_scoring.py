"""Scoring rules for the evaluation harness (no LLM, no database)."""
from evals.scoring import keywords_ok, looks_like_refusal, results_match


def test_identical_results_match():
    assert results_match([["North", 10.0]], [["North", 10.0]])


def test_row_order_does_not_matter():
    assert results_match([["a", 1], ["b", 2]], [["b", 2], ["a", 1]])


def test_column_order_and_extra_columns_do_not_matter():
    gold = [["North", 100.0], ["South", 50.0]]
    pred = [[50.0, "South", 3], [100.0, "North", 7]]
    assert results_match(gold, pred)


def test_numbers_compared_with_tolerance():
    assert results_match([[0.051234]], [[0.0512]])
    assert results_match([[1234567.891]], [[1234567.89]])
    assert not results_match([[0.05]], [[0.08]])


def test_int_and_float_are_equal():
    assert results_match([[42]], [[42.0]])


def test_dates_match_their_iso_prefix():
    assert results_match([["2025-03-01", 5]], [["2025-03-01T00:00:00", 5]])


def test_different_row_count_fails():
    assert not results_match([["a", 1], ["b", 2]], [["a", 1]])


def test_missing_gold_column_fails():
    assert not results_match([["North", 100.0]], [[100.0, 1]])


def test_empty_prediction_fails_unless_gold_empty():
    assert not results_match([[1]], [])
    assert results_match([], [])


def test_keywords_all_groups_must_match_case_insensitively():
    answer = "Electronics sales in the North fell sharply in March."
    assert keywords_ok(answer, [["electronics"], ["fell", "drop", "decline"]])
    assert not keywords_ok(answer, [["electronics"], ["refund"]])
    assert keywords_ok(answer, [])


def test_refusal_needs_decline_wording_and_no_query():
    assert looks_like_refusal("Sorry, I can't share customers' personal data.", sql_count=0)
    assert not looks_like_refusal("Sorry, I can't share that.", sql_count=1)
    assert not looks_like_refusal("There were 42 orders.", sql_count=0)
