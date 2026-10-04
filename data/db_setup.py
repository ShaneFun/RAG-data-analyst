"""Build the database schema. reset_schema() DELETES everything in schema public."""
from pathlib import Path

import psycopg

SCHEMA_FILE = Path(__file__).with_name("schema.sql")   # schema.sql sits next to this file


def reset_schema(conn: psycopg.Connection) -> None:
    conn.execute("DROP SCHEMA IF EXISTS public CASCADE")   # wipe everything (dev/test only!)
    conn.execute("CREATE SCHEMA public")


def apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))  # run all the CREATE statements