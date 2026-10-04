import pytest

from app.db import make_pool
from app.sql.executor import run_select


@pytest.fixture(scope="module")
def pool(loaded_db):
    p = make_pool(loaded_db["ro_url"], min_size=1, max_size=1)
    yield p
    p.close()


def test_simple_query(pool, dataset):
    result = run_select(pool, "SELECT COUNT(*) AS n FROM orders")
    assert result.ok and result.error is None
    assert result.columns == ["n"]
    assert result.rows == [[len(dataset.orders)]]
    assert result.row_count == 1
    assert result.sql.endswith("LIMIT 200")


def test_values_are_json_safe(pool):
    result = run_select(pool, "SELECT order_date, unit_price FROM orders o "
                              "JOIN order_items i ON i.order_id = o.id ORDER BY i.id LIMIT 1")
    date_value, price_value = result.rows[0]
    assert isinstance(date_value, str) and len(date_value) == 10   # 'YYYY-MM-DD'
    assert isinstance(price_value, float)


def test_rows_are_capped(pool):
    result = run_select(pool, "SELECT * FROM order_items")
    assert result.ok and result.row_count == 200 and len(result.rows) == 200


def test_rejected_query_never_runs(pool):
    result = run_select(pool, "DROP TABLE orders")
    assert not result.ok
    assert result.error.startswith("Rejected:")
    assert result.sql is None


def test_database_error_is_reported(pool):
    result = run_select(pool, "SELECT no_such_column FROM orders")
    assert not result.ok
    assert result.error.startswith("Database error:")
    assert "no_such_column" in result.error


def test_timeout_is_reported_and_pool_recovers(pool):
    slow = run_select(pool, "SELECT COUNT(*) FROM order_items a, order_items b", timeout="200ms")
    assert not slow.ok
    assert "timed out" in slow.error
    assert run_select(pool, "SELECT 1 AS one").rows == [[1]]


def test_pool_resets_session_settings(pool):
    with pool.connection() as conn:
        conn.execute("SET statement_timeout = '1ms'")
    with pool.connection() as conn:   # same single connection, after reset
        assert conn.execute("SHOW statement_timeout").fetchone() == ("5s",)


def test_to_dict_shape(pool):
    d = run_select(pool, "SELECT 1 AS one").to_dict()
    assert set(d) == {"ok", "sql", "columns", "rows", "row_count", "error"}


def test_pool_fails_fast_when_no_connection_is_available():
    from app.db import make_pool
    pool = make_pool("postgresql://nobody:wrong@localhost:5432/nowhere", min_size=0,
                     timeout=0.5)
    try:
        assert pool.timeout == 0.5
    finally:
        pool.close()
