"""Embed knowledge entries and (re)fill the knowledge tables."""
import psycopg
from pgvector.psycopg import register_vector

from app.knowledge.embed import Embedder
from data.knowledge_entries import KnowledgeEntry


def entry_text(entry: KnowledgeEntry) -> str:
    """Text that gets embedded. Example content already starts with its question; handbook
    titles carry the heading path ("Refunds > Refund policy"), so each chunk keeps its context."""
    return entry.content if entry.kind == "example" else f"{entry.title}\n{entry.content}"


def load_knowledge(conn: psycopg.Connection, entries: list[KnowledgeEntry], embedder: Embedder,
                   sections: list[tuple[str, str]] = ()) -> int:
    """sections: the handbook's parent sections [(title, content)]; stored, not embedded."""
    register_vector(conn)
    vectors = embedder.embed_passages([entry_text(e) for e in entries])
    with conn.transaction():
        # wipe old entries -> safe to re-run
        conn.execute("TRUNCATE knowledge, knowledge_sections RESTART IDENTITY")
        section_ids = {}
        for title, content in sections:
            section_ids[title] = conn.execute(
                "INSERT INTO knowledge_sections (title, content) VALUES (%s, %s) RETURNING id",
                (title, content)).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO knowledge (kind, title, content, section_id, embedding) "
                "VALUES (%s, %s, %s, %s, %s)",
                [(e.kind, e.title, e.content, section_ids.get(e.section), v)
                 for e, v in zip(entries, vectors, strict=True)],
            )
    return len(entries)
