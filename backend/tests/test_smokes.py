import psycopg

from app.config import Settings
from tests.helpers import ensure_database


def test_settings_have_local_defaults():
    s = Settings(_env_file=None)
    assert s.database_url_admin.startswith("postgresql://postgres:")
    assert s.database_url_ro.startswith("postgresql://analyst_ro:")
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.sql_timeout == "5s"
    assert s.max_rows == 200


def test_can_connect_to_test_database():
    url = ensure_database("larkspur_test")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT 1").fetchone() == (1,)