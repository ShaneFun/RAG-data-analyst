"""The retrieval evaluation must be valid: every expected title exists in the knowledge base."""
import psycopg

from data.knowledge_entries import load_entries, load_sections
from evals.retrieval import evaluate, first_relevant_rank, load_retrieval_questions


def test_first_relevant_rank():
    assert first_relevant_rank(["a", "b", "c"], ["c", "b"]) == 2
    assert first_relevant_rank(["a"], ["z"]) is None


def test_every_relevant_title_exists():
    titles = {e.title for e in load_entries() if e.kind != "handbook"}
    titles |= {title for title, _ in load_sections()}
    for item in load_retrieval_questions():
        assert set(item["relevant"]) <= titles, item["query"]


def test_evaluate_reports_metrics_for_each_mode(knowledge_db, embedder):
    items = load_retrieval_questions()[:3]
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        for mode in ("vector", "keyword", "hybrid"):
            result = evaluate(conn, embedder, items, mode)
            assert 0 <= result["mrr"] <= result["recall@5"] <= 1
