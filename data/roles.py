"""Privacy view + read-only role used to run agent SQL."""
import psycopg
from psycopg import sql

READ_TABLES = ("customers_safe", "products", "orders", "order_items", "refunds")
# The knowledge base is metadata, not customer data. Letting the read-only role read it means
# the running API needs no admin credentials at all. The agent's own SQL still can't reach it:
# the validator only allows READ_TABLES.
KNOWLEDGE_TABLES = ("knowledge", "knowledge_sections")


def setup_roles(conn: psycopg.Connection, ro_password: str, timeout: str = "5s") -> None:
    # Privacy view: customers WITHOUT full_name and email.
    conn.execute(
        "CREATE OR REPLACE VIEW customers_safe AS "
        "SELECT id, region, signup_date, signup_channel FROM customers"
    )
    # Create the read-only login (or update its password if it already exists).
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'analyst_ro'").fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(sql.SQL(verb + " ROLE analyst_ro WITH LOGIN PASSWORD {}").format(
        sql.Literal(ro_password)))
    # Extra safety settings that apply to every session of this user.
    conn.execute(sql.SQL("ALTER ROLE analyst_ro SET statement_timeout = {}").format(
        sql.Literal(timeout)))
    conn.execute("ALTER ROLE analyst_ro SET default_transaction_read_only = on")
    # Least privilege: start from zero, then allow SELECT on exactly five objects.
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO analyst_ro").format(
        sql.Identifier(conn.info.dbname)))
    conn.execute("GRANT USAGE ON SCHEMA public TO analyst_ro")
    conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst_ro")
    for table in READ_TABLES + KNOWLEDGE_TABLES:
        conn.execute(sql.SQL("GRANT SELECT ON {} TO analyst_ro").format(sql.Identifier(table)))
