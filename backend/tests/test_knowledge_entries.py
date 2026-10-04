from collections import Counter

import psycopg
import pytest

from data.knowledge_entries import load_entries, load_examples
from data.roles import READ_TABLES


def test_entry_counts_by_kind():
    counts = Counter(e.kind for e in load_entries())
    assert counts == {"dictionary": 5, "glossary": 9, "example": 15}


def test_titles_are_unique_and_content_not_empty():
    entries = load_entries()
    assert len({e.title for e in entries}) == len(entries)
    assert all(e.content.strip() for e in entries)


def test_dictionary_covers_exactly_the_readable_tables():
    titles = {e.title for e in load_entries() if e.kind == "dictionary"}
    assert titles == set(READ_TABLES)


def test_example_content_contains_question_and_sql():
    for entry in (e for e in load_entries() if e.kind == "example"):
        assert entry.content.startswith(f"Question: {entry.title}\nSQL:\n")


@pytest.mark.parametrize("example", load_examples(), ids=lambda e: e["question"][:40])
def test_every_example_sql_runs_as_read_only_role(loaded_db, example):
    with psycopg.connect(loaded_db["ro_url"]) as conn:
        rows = conn.execute(example["sql"]).fetchall()
    assert rows, "example query returned no rows"
