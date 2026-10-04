"""Build the development database from scratch.

Usage (from the repo root):  uv run --project backend python -m data.setup_db
WARNING: drops and recreates everything in schema public.
"""
import psycopg

from app.config import get_settings
from app.knowledge.embed import Embedder
from data.db_setup import apply_schema, reset_schema
from data.generate import generate
from data.knowledge_entries import load_entries, load_sections
from data.load_data import load_dataset
from data.load_knowledge import load_knowledge
from data.roles import setup_roles


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url_admin, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        counts = load_dataset(conn, generate(seed=42))
        setup_roles(conn, settings.analyst_ro_password, settings.sql_timeout)
        counts["knowledge"] = load_knowledge(conn, load_entries(),
                                             Embedder(settings.embedding_model), load_sections())
    print("Loaded:", counts)


if __name__ == "__main__":
    main()
