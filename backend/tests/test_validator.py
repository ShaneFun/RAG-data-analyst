import pytest

from app.sql.validator import validate_sql
from data.knowledge_entries import load_examples

ALLOWED = [
    "SELECT region, COUNT(*) FROM orders GROUP BY region",
    ("WITH m AS (SELECT DATE_TRUNC('month', order_date) AS mo, COUNT(*) c FROM orders GROUP BY 1) "
     "SELECT * FROM m ORDER BY mo"),
    "SELECT id FROM orders UNION SELECT id FROM refunds",
    "SELECT * FROM public.orders",
    ("SELECT * FROM orders o JOIN order_items i ON i.order_id = o.id "
     "JOIN products p ON p.id = i.product_id WHERE p.category = 'Electronics'"),
    "SELECT * FROM customers_safe",
]

BLOCKED = [
    ("DROP TABLE orders", "Only SELECT"),
    ("DELETE FROM orders", "Only SELECT"),
    ("INSERT INTO orders VALUES (1)", "Only SELECT"),
    ("UPDATE orders SET status = 'x'", "Only SELECT"),
    ("COPY orders TO '/tmp/x'", "Only SELECT"),
    ("SELECT 1; DROP TABLE orders", "one SQL statement"),
    ("SELECT * FROM customers", "Table not allowed"),
    ("SELECT id FROM orders WHERE customer_id IN (SELECT id FROM customers)", "Table not allowed"),
    ("SELECT * FROM pg_catalog.pg_tables", "Table not allowed"),
    ("SELECT * FROM information_schema.tables", "Table not allowed"),
    ("SELECT * INTO newtab FROM orders", "Forbidden operation"),
    ("SELECT * FROM orders FOR UPDATE", "Forbidden operation"),
    ("SELECT pg_sleep(10)", "Function not allowed"),
    ("SELECT set_config('statement_timeout', '0', false)", "Function not allowed"),
    ("SELECT * FROM generate_series(1, 10)", "Table functions"),
    ("SELEC * FROM orders", "Could not parse"),
    ("", "Empty query"),
    ("   \n  ", "Empty query"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_queries_pass(sql):
    result = validate_sql(sql)
    assert result.ok, result.error
    assert result.error is None


@pytest.mark.parametrize("sql,reason", BLOCKED)
def test_blocked_queries_are_rejected(sql, reason):
    result = validate_sql(sql)
    assert not result.ok
    assert result.sql is None
    assert reason in result.error


def test_missing_limit_is_added():
    assert validate_sql("SELECT * FROM orders").sql == "SELECT * FROM orders LIMIT 200"


def test_small_limit_is_kept():
    assert validate_sql("select * from orders limit 10").sql == "SELECT * FROM orders LIMIT 10"


def test_large_limit_is_capped():
    assert validate_sql("SELECT * FROM orders LIMIT 5000").sql == "SELECT * FROM orders LIMIT 200"


def test_union_is_wrapped_and_limited():
    sql = validate_sql("SELECT id FROM orders UNION SELECT id FROM refunds").sql
    assert sql == "SELECT * FROM (SELECT id FROM orders UNION SELECT id FROM refunds) AS q LIMIT 200"


def test_custom_max_rows():
    assert validate_sql("SELECT * FROM orders", max_rows=5).sql.endswith("LIMIT 5")


@pytest.mark.parametrize("example", load_examples(), ids=lambda e: e["question"][:40])
def test_all_knowledge_examples_pass_validator(example):
    assert validate_sql(example["sql"]).ok


@pytest.mark.parametrize("sql", ["SELECT * FROM knowledge", "SELECT * FROM knowledge_sections"])
def test_agent_sql_cannot_read_the_knowledge_tables(sql):
    assert not validate_sql(sql).ok
