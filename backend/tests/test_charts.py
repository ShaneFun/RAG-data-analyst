from app.charts import chart_hint


def test_line_for_dates():
    hint = chart_hint(["month", "orders"], [["2025-01-01", 300], ["2025-02-01", 310]])
    assert hint == {"type": "line", "x": "month", "y": "orders"}


def test_line_for_year_month_strings():
    assert chart_hint(["month", "n"], [["2025-01", 1], ["2025-02", 2]])["type"] == "line"


def test_bar_for_categories():
    hint = chart_hint(["category", "units", "revenue"], [["Home", 5, 50.0], ["Beauty", 3, 9.5]])
    assert hint == {"type": "bar", "x": "category", "y": "units"}


def test_none_for_too_many_categories():
    rows = [[f"p{i}", i] for i in range(25)]
    assert chart_hint(["product", "n"], rows)["type"] == "none"


def test_none_for_single_value_or_no_numbers():
    assert chart_hint(["n"], [[10005]])["type"] == "none"
    assert chart_hint(["a", "b"], [["x", "y"]])["type"] == "none"
    assert chart_hint(["a", "b"], [])["type"] == "none"


def test_booleans_are_not_numbers():
    assert chart_hint(["a", "flag"], [["x", True]])["type"] == "none"


def test_none_when_the_first_column_repeats():
    # several suppliers per month: one line through all rows would be meaningless
    rows = [["2025-01", "Brightline Goods", 3332.6], ["2025-02", "Brightline Goods", 3106.4],
            ["2025-01", "Copperleaf Trading", 4105.8]]
    assert chart_hint(["month", "supplier", "revenue"], rows)["type"] == "none"
    assert chart_hint(["region", "n"], [["North", 1], ["North", 2]])["type"] == "none"
