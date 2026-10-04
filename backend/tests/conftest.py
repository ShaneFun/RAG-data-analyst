"""Shared pytest fixtures."""
import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from app.config import Settings
from app.knowledge.embed import Embedder
from data.db_setup import apply_schema, reset_schema
from data.generate import generate
from data.knowledge_entries import load_entries, load_sections
from data.load_data import load_dataset
from data.load_knowledge import load_knowledge
from data.roles import setup_roles
from tests.helpers import ensure_database

# Postgres roles are shared by every database on the server, so the test database must use the
# same analyst_ro password as the dev database (otherwise running the tests breaks the app).
RO_PASSWORD = Settings().analyst_ro_password


@pytest.fixture(scope="session")
def dataset():
    return generate(seed=42)


@pytest.fixture(scope="session")
def loaded_db(dataset):
    """Test database with schema + data + roles, built once per test run."""
    admin_url = ensure_database("larkspur_test")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        reset_schema(conn)
        apply_schema(conn)
        load_dataset(conn, dataset)
        setup_roles(conn, RO_PASSWORD, timeout="5s")
    ro_url = make_conninfo(admin_url, user="analyst_ro", password=RO_PASSWORD)
    return {"admin_url": admin_url, "ro_url": ro_url}


@pytest.fixture(scope="session")
def embedder():
    return Embedder()  # downloads ~70 MB on first run, cached afterwards


@pytest.fixture(scope="session")
def knowledge_db(loaded_db, embedder):
    """loaded_db + the knowledge base (29 curated entries + 20 handbook chunks) in pgvector."""
    with psycopg.connect(loaded_db["admin_url"], autocommit=True) as conn:
        load_knowledge(conn, load_entries(), embedder, load_sections())
    return loaded_db
