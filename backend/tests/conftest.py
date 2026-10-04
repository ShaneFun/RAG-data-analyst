"""Shared pytest fixtures."""
import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from data.db_setup import apply_schema, reset_schema
from data.generate import generate
from data.load_data import load_dataset
from data.roles import setup_roles
from tests.helpers import ensure_database

RO_PASSWORD = "analyst_ro_test"


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
