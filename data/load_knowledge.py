"""Embed knowledge entries and (re)fill the knowledge table."""
import psycopg
from pgvector.psycopg import register_vector

from app.knowledge.embed import Embedder
from data.knowledge_entries import KnowledgeEntry


def entry_text(entry: KnowledgeEntry) -> str:
    """Text that gets embedded. Example content already starts with its question."""
    return entry.content if entry.kind == "example" else f"{entry.title}\n{entry.content}"


def load_knowledge(conn: psycopg.Connection, entries: list[KnowledgeEntry],
                   embedder: Embedder) -> int:
    register_vector(conn)
    vectors = embedder.embed_passages([entry_text(e) for e in entries])
    with conn.transaction():
        conn.execute("TRUNCATE knowledge RESTART IDENTITY")  # wipe old entries -> safe to re-run
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO knowledge (kind, title, content, embedding) VALUES (%s, %s, %s, %s)",
                [(e.kind, e.title, e.content, v) for e, v in zip(entries, vectors)],
            )
    return len(entries)
