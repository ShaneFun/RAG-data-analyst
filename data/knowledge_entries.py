"""Read the knowledge-base YAML sources (metadata about the data, never the data itself)."""
from dataclasses import dataclass
from pathlib import Path

import yaml

KNOWLEDGE_DIR = Path(__file__).with_name("knowledge")


@dataclass(frozen=True)
class KnowledgeEntry:
    kind: str     # "dictionary" | "glossary" | "example"
    title: str
    content: str


def _read(directory: Path, name: str) -> list[dict]:
    return yaml.safe_load((directory / name).read_text(encoding="utf-8"))


def load_examples(directory: Path = KNOWLEDGE_DIR) -> list[dict]:
    """The raw example pairs: [{"question": ..., "sql": ...}, ...]."""
    return _read(directory, "examples.yaml")


def load_entries(directory: Path = KNOWLEDGE_DIR) -> list[KnowledgeEntry]:
    """All 29 entries in one format, ready to be embedded."""
    entries = [KnowledgeEntry("dictionary", d["title"], d["content"].strip())
               for d in _read(directory, "dictionary.yaml")]
    entries += [KnowledgeEntry("glossary", g["title"], g["content"].strip())
                for g in _read(directory, "glossary.yaml")]
    entries += [KnowledgeEntry("example", e["question"],
                               f"Question: {e['question']}\nSQL:\n{e['sql'].strip()}")
                for e in load_examples(directory)]
    return entries
