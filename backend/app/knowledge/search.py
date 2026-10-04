"""Hybrid search over the knowledge base.

query ─┬─ vector search (pgvector cosine, meaning)     ─┐
       └─ keyword search (BM25, exact words like "AOV") ─┴─ RRF fusion ─ parent expansion ─ top k

- RRF (reciprocal rank fusion) merges the two ranked lists using ranks only, so the two
  incompatible scores (cosine vs BM25) never have to be compared.
- Parent expansion: handbook chunks are small so they match precisely, but the LLM gets the
  whole parent section for context ("search small, read big"). Duplicates are removed.
- kind filter (metadata filtering) restricts both retrievers to one kind of entry.
"""
import re
from dataclasses import dataclass
from typing import Literal

import psycopg
from pgvector.psycopg import register_vector
from rank_bm25 import BM25Okapi

from app.knowledge.embed import Embedder

Kind = Literal["dictionary", "glossary", "example", "handbook"]
Mode = Literal["hybrid", "vector", "keyword"]

RRF_K = 60          # standard constant from the RRF paper: damps the advantage of rank 1
CANDIDATES = 20     # how many results each retriever contributes before fusion

STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "did", "for", "from", "has",
    "have", "how", "i", "in", "is", "it", "many", "much", "of", "on", "or", "per", "show",
    "than", "that", "the", "their", "there", "this", "to", "was", "we", "were", "what", "when",
    "where", "which", "who", "why", "with", "you",
})


@dataclass(frozen=True)
class KnowledgeHit:
    kind: str
    title: str
    content: str
    score: float  # higher = more relevant (RRF score in hybrid mode, else cosine / BM25)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t not in STOPWORDS]


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(id) = sum over lists of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


def _vector_ranking(conn, embedder: Embedder, query: str, kind: str | None,
                    n: int) -> list[tuple[int, float]]:
    register_vector(conn)  # let psycopg send numpy vectors to pgvector
    vector = embedder.embed_query(query)
    return conn.execute(
        "SELECT id, 1 - (embedding <=> %s) FROM knowledge "      # <=> = cosine distance
        "WHERE %s::text IS NULL OR kind = %s "
        "ORDER BY embedding <=> %s LIMIT %s",                    # closest first
        (vector, kind, kind, vector, n),
    ).fetchall()


def _keyword_ranking(rows: list[tuple], query: str, n: int) -> list[tuple[int, float]]:
    # The corpus is ~50 short entries, so BM25 is rebuilt per query (microseconds).
    # At scale this would move into the database (Postgres full-text search or pg_search).
    tokens = tokenize(query)
    if not rows or not tokens:
        return []
    bm25 = BM25Okapi([tokenize(f"{title} {content}") for _, _, title, content, *_ in rows])
    scored = sorted(zip((r[0] for r in rows), bm25.get_scores(tokens), strict=True),
                    key=lambda pair: pair[1], reverse=True)
    return [(i, float(s)) for i, s in scored[:n] if s > 0]


def search_knowledge(conn: psycopg.Connection, embedder: Embedder, query: str, k: int = 5,
                     kind: Kind | None = None, mode: Mode = "hybrid") -> list[KnowledgeHit]:
    if not query.strip():
        return []  # blank question -> nothing, no crash
    rows = conn.execute(
        "SELECT k.id, k.kind, k.title, k.content, s.title, s.content "
        "FROM knowledge k LEFT JOIN knowledge_sections s ON s.id = k.section_id "
        "WHERE %s::text IS NULL OR k.kind = %s", (kind, kind)).fetchall()
    by_id = {r[0]: r for r in rows}

    vector = _vector_ranking(conn, embedder, query, kind, CANDIDATES) if mode != "keyword" else []
    keyword = _keyword_ranking(rows, query, CANDIDATES) if mode != "vector" else []
    if mode == "hybrid":
        ranked = rrf([[i for i, _ in vector], [i for i, _ in keyword]])
    else:
        ranked = vector or keyword

    hits, seen = [], set()
    for entry_id, score in ranked:
        _, entry_kind, title, content, section_title, section_content = by_id[entry_id]
        if section_title:  # handbook chunk -> return its whole parent section
            title, content = section_title, section_content
        if title in seen:
            continue
        seen.add(title)
        hits.append(KnowledgeHit(entry_kind, title, content, float(score)))
        if len(hits) == k:
            break
    return hits
