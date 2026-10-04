from collections import Counter

import psycopg
import pytest

from data.knowledge_entries import load_entries, load_examples, load_sections
from data.roles import READ_TABLES


def test_entry_counts_by_kind():
    counts = Counter(e.kind for e in load_entries())
    assert counts == {"dictionary": 5, "glossary": 9, "example": 15, "handbook": 20}


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


# --- Handbook: header-based chunking + parent-child ---

def _handbook():
    return [e for e in load_entries() if e.kind == "handbook"]


def test_handbook_is_split_into_7_parent_sections():
    titles = [title for title, _ in load_sections()]
    assert len(titles) == 7 and titles[0] == "About Larkspur Market"


def test_each_chunk_is_a_subsection_with_its_heading_path():
    sections = dict(load_sections())
    for chunk in _handbook():
        section, _, subsection = chunk.title.partition(" > ")
        assert chunk.section == section and section in sections and subsection
        assert len(chunk.content) < 1200                  # small enough to embed precisely
        assert chunk.content in sections[section]          # the parent contains the child
        assert f"### {subsection}" in sections[section]


def test_curated_entries_have_no_parent_section():
    assert all(e.section is None for e in load_entries() if e.kind != "handbook")


def test_handbook_does_not_leak_the_planted_trends():
    text = " ".join(content for _, content in load_sections()).lower()
    for hint in ("holiday", "stock", "spike", "peak", "seasonal", "march 2025"):
        assert hint not in text, hint
