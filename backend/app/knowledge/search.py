"""Semantic search over the knowledge table (cosine similarity via pgvector)."""
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from app.knowledge.embed import Embedder


@dataclass(frozen=True)
class KnowledgeHit:
    kind: str
    title: str
    content: str
    score: float  # cosine similarity, higher = more relevant


def search_knowledge(conn: psycopg.Connection, embedder: Embedder, query: str,
                     k: int = 5) -> list[KnowledgeHit]:
    if not query.strip():
        return []  # blank question -> nothing, no crash
    register_vector(conn)  # let psycopg send numpy vectors to pgvector
    vector = embedder.embed_query(query)
    rows = conn.execute(
        "SELECT kind, title, content, 1 - (embedding <=> %s) AS score "  # <=> = cosine distance
        "FROM knowledge ORDER BY embedding <=> %s LIMIT %s",             # closest first, top k
        (vector, vector, k),
    ).fetchall()
    return [KnowledgeHit(kind, title, content, float(score)) for kind, title, content, score in rows]
