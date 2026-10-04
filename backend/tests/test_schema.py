import psycopg
import pytest

from data.db_setup import apply_schema, reset_schema
from tests.helpers import ensure_database

EXPECTED_TABLES = {"customers", "products", "orders", "order_items", "refunds", "knowledge"}
EXPECTED_INDEXES = {
    "idx_orders_order_date", "idx_orders_region", "idx_orders_customer_id",
    "idx_order_items_order_id", "idx_order_items_product_id",
    "idx_products_category", "idx_products_supplier",
}


@pytest.fixture
def schema_conn():
    url = ensure_database("larkspur_test_schema")
    with psycopg.connect(url, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        yield conn


def test_all_tables_exist(schema_conn):
    rows = schema_conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    assert EXPECTED_TABLES <= {r[0] for r in rows}


def test_indexes_exist(schema_conn):
    rows = schema_conn.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
    ).fetchall()
    assert EXPECTED_INDEXES <= {r[0] for r in rows}


def test_knowledge_embedding_is_384_dim_vector(schema_conn):
    row = schema_conn.execute(
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = 'knowledge'::regclass AND attname = 'embedding'"
    ).fetchone()
    assert row == ("vector(384)",)


def test_apply_schema_is_repeatable(schema_conn):
    reset_schema(schema_conn)
    apply_schema(schema_conn)  # building twice must not fail