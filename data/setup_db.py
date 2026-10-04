"""Build the development database from scratch.

Usage (from the repo root):  uv run --project backend python -m data.setup_db
WARNING: drops and recreates everything in schema public.
"""
import psycopg

from app.config import get_settings
from data.db_setup import apply_schema, reset_schema
from data.generate import generate
from data.load_data import load_dataset
from data.roles import setup_roles


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url_admin, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        counts = load_dataset(conn, generate(seed=42))
        setup_roles(conn, settings.analyst_ro_password, settings.sql_timeout)
    print("Loaded:", counts)


if __name__ == "__main__":
    main()
