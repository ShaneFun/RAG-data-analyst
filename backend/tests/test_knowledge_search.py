import psycopg

from app.knowledge.search import rrf, search_knowledge, tokenize
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
        assert conn.execute("SELECT COUNT(*) FROM knowledge").fetchone() == (49,)
        assert conn.execute("SELECT COUNT(*) FROM knowledge_sections").fetchone() == (7,)
        orphans = conn.execute("SELECT COUNT(*) FROM knowledge "
                               "WHERE (kind = 'handbook') <> (section_id IS NOT NULL)").fetchone()
        assert orphans == (0,)


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
    # the handbook section saying "the supplier is stored on the products table" may rank first
    assert "products" in _titles(hits)[:2]
    assert {h.title for h in hits[:2]} <= {"products", "About Larkspur Market"}


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


# --- Hybrid search: BM25 + vectors fused with RRF, parent expansion, metadata filter ---

def test_rrf_rewards_items_ranked_well_in_both_lists():
    # 1 is 1st and 2nd; 3 is 1st and 3rd; 2 appears once
    assert [i for i, _ in rrf([[1, 2, 3], [3, 1]])] == [1, 3, 2]
    scores = dict(rrf([[1, 2, 3], [3, 1]]))
    assert scores[1] == 1 / 61 + 1 / 62


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("What is the AOV of App orders?") == ["aov", "app", "orders"]


def _search(knowledge_db, embedder, query, **kwargs):
    with psycopg.connect(knowledge_db["admin_url"]) as conn:
        return search_knowledge(conn, embedder, query, **kwargs)


def test_keyword_search_matches_exact_abbreviation(knowledge_db, embedder):
    hits = _search(knowledge_db, embedder, "AOV", mode="keyword")
    assert "Average order value (AOV)" in _titles(hits)[:2]


def test_handbook_hit_returns_the_whole_parent_section(knowledge_db, embedder):
    hits = _search(knowledge_db, embedder, "how many days do customers have to return an item")
    refunds = next(h for h in hits if h.kind == "handbook")
    assert refunds.title == "Refunds"
    assert "### Refund policy" in refunds.content and "### Refund reasons" in refunds.content


def test_results_are_deduplicated_by_parent(knowledge_db, embedder):
    hits = _search(knowledge_db, embedder, "refund policy refund reasons refund dates", k=8)
    assert len(_titles(hits)) == len(set(_titles(hits)))


def test_kind_filter_applies_to_both_retrievers(knowledge_db, embedder):
    for mode in ("vector", "keyword", "hybrid"):
        hits = _search(knowledge_db, embedder, "revenue by region", kind="example", mode=mode)
        assert hits and {h.kind for h in hits} == {"example"}, mode


def test_every_mode_returns_k_hits(knowledge_db, embedder):
    for mode in ("vector", "keyword", "hybrid"):
        assert len(_search(knowledge_db, embedder, "refund rate by supplier", k=4, mode=mode)) == 4
