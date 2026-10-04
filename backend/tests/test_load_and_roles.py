import psycopg
import pytest
from psycopg import errors


def test_row_counts_match_dataset(loaded_db, dataset):
    with psycopg.connect(loaded_db["admin_url"]) as conn:
        for table in ("customers", "products", "orders", "order_items", "refunds"):
            (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            assert count == len(getattr(dataset, table)), table


def test_t3_visible_in_database(loaded_db):
    query = """
        SELECT EXTRACT(MONTH FROM o.order_date)::int AS m, COUNT(DISTINCT o.id)
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        JOIN products p ON p.id = oi.product_id
        WHERE o.region = 'North' AND p.category = 'Electronics'
          AND o.order_date >= '2025-02-01' AND o.order_date < '2025-05-01'
        GROUP BY 1
    """
    with psycopg.connect(loaded_db["admin_url"]) as conn:
        by_month = dict(conn.execute(query).fetchall())
    assert by_month[3] <= 0.40 * (by_month[2] + by_month[4]) / 2


def test_read_only_role_can_read_allowed_tables(loaded_db, dataset):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        (count,) = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        assert count == len(dataset.orders)
        cols = conn.execute("SELECT * FROM customers_safe LIMIT 1").description
        assert [c.name for c in cols] == ["id", "region", "signup_date", "signup_channel"]


@pytest.mark.parametrize("query", [
    "SELECT * FROM customers",
    "SELECT email FROM customers",
])
def test_read_only_role_cannot_read_private_tables(loaded_db, query):
    with psycopg.connect(loaded_db["ro_url"]) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute(query)


def test_read_only_role_can_read_knowledge_so_the_api_needs_no_admin_password(loaded_db):
    # knowledge is metadata (not customer data); the SQL validator still stops the AGENT's
    # queries from touching it, so only search_knowledge reads it
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        conn.execute("SELECT id FROM knowledge LIMIT 1")
        conn.execute("SELECT id FROM knowledge_sections LIMIT 1")
    denied = (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)
    with psycopg.connect(loaded_db["ro_url"]) as conn, pytest.raises(denied):
        conn.execute("DELETE FROM knowledge")


@pytest.mark.parametrize("query", [
    "INSERT INTO orders VALUES (999999, 1, '2025-01-01', 'web', 'North', 'completed')",
    "UPDATE orders SET status = 'cancelled'",
    "DELETE FROM refunds",
    "DROP TABLE orders",
    "CREATE TABLE hack (id int)",
])
def test_read_only_role_cannot_write(loaded_db, query):
    denied = (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)
    with psycopg.connect(loaded_db["ro_url"]) as conn, pytest.raises(denied):
        conn.execute(query)


def test_read_only_role_has_timeout_and_read_only_default(loaded_db):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        assert conn.execute("SHOW statement_timeout").fetchone() == ("5s",)
        assert conn.execute("SHOW default_transaction_read_only").fetchone() == ("on",)
