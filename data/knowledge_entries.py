"""Read the knowledge-base YAML sources (metadata about the data, never the data itself)."""
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from langchain_text_splitters import MarkdownHeaderTextSplitter

KNOWLEDGE_DIR = Path(__file__).with_name("knowledge")


@dataclass(frozen=True)
class KnowledgeEntry:
    kind: str     # "dictionary" | "glossary" | "example" | "handbook"
    title: str
    content: str
    section: str | None = None   # handbook chunks: title of the parent section


def _read(directory: Path, name: str) -> list[dict]:
    return yaml.safe_load((directory / name).read_text(encoding="utf-8"))


def load_examples(directory: Path = KNOWLEDGE_DIR) -> list[dict]:
    """The raw example pairs: [{"question": ..., "sql": ...}, ...]."""
    return _read(directory, "examples.yaml")


@cache
def _handbook_chunks(path: Path) -> tuple[tuple[str, str, str], ...]:
    """Header-based chunking: one chunk per ### subsection, tagged with its ## section."""
    splitter = MarkdownHeaderTextSplitter([("##", "section"), ("###", "subsection")])
    docs = splitter.split_text(path.read_text(encoding="utf-8"))
    return tuple((d.metadata["section"], d.metadata["subsection"], d.page_content.strip())
                 for d in docs if "subsection" in d.metadata)


def load_sections(directory: Path = KNOWLEDGE_DIR) -> list[tuple[str, str]]:
    """Parent sections [(title, full text)], rebuilt from their chunks, in document order."""
    sections: dict[str, list[str]] = {}
    for section, subsection, text in _handbook_chunks(directory / "handbook.md"):
        sections.setdefault(section, []).append(f"### {subsection}\n{text}")
    return [(title, "\n\n".join(parts)) for title, parts in sections.items()]


def load_entries(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeEntry]:
    """29 curated entries + the handbook's 20 chunks, in one format, ready to be embedded."""
    entries = [KnowledgeEntry("dictionary", d["title"], d["content"].strip())
               for d in _read(directory, "dictionary.yaml")]
    entries += [KnowledgeEntry("glossary", g["title"], g["content"].strip())
                for g in _read(directory, "glossary.yaml")]
    entries += [KnowledgeEntry("example", e["question"],
                               f"Question: {e['question']}\nSQL:\n{e['sql'].strip()}")
                for e in load_examples(directory)]
    entries += [KnowledgeEntry("handbook", f"{section} > {subsection}", text, section)
                for section, subsection, text in _handbook_chunks(directory / "handbook.md")]
    return entries
