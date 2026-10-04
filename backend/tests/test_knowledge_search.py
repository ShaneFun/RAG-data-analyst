import psycopg

from app.knowledge.search import search_knowledge
from data.knowledge_entries import KnowledgeEntry
from data.load_knowledge import entry_text


def _titles(hits):
    return [h.title for h in hits]


def test_embedder_returns_384_dims(embedder):
    assert embedder.embed_query("revenue").shape == (384,)
    assert [v.shape for v in embedder.embed_passages(["a", "b"])] == [(384,), (384,)]


def test_entry_text_format():
    glossary = KnowledgeEntry("glossary", "Units sold", "SUM(quantity)")
    assert entry_text(glossary) == "Units sold\nSUM(quantity)"
    example = KnowledgeEntry("example", "Q?", "Question: Q?\nSQL:\nSELECT 1")
    assert entry_text(example) == "Question: Q?\nSQL:\nSELECT 1"


def test_all_entries_loaded(knowledge_db):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM knowledge").fetchone() == (29,)


def test_revenue_finds_gross_revenue_definition(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "revenue")
    assert "Gross revenue (sales)" in _titles(hits)


def test_aov_is_top_hit(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "average order value")
    assert hits[0].title == "Average order value (AOV)"


def test_supplier_question_finds_products_table(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "which table has the supplier?")
    assert hits[0].kind == "dictionary" and hits[0].title == "products"


def test_k_and_score_order(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        hits = search_knowledge(conn, embedder, "orders by month", k=3)
    assert len(hits) == 3
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
    assert all(isinstance(s, float) for s in scores)


def test_blank_query_returns_nothing(knowledge_db, embedder):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        assert search_knowledge(conn, embedder, "   ") == []
