import os

import psycopg
from psycopg import sql

ADMIN_BASE = os.environ.get("TEST_PG_ADMIN", "postgresql://postgres:postgres@localhost:5432")


def ensure_database(name: str) -> str:
    """Create the database if missing and return an admin URL for it."""
    with psycopg.connect(f"{ADMIN_BASE}/postgres", autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    return f"{ADMIN_BASE}/{name}"