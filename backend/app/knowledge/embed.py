"""Text embeddings with FastEmbed (BAAI/bge-small-en-v1.5, 384 dimensions, runs locally)."""
import numpy as np
from fastembed import TextEmbedding

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model = TextEmbedding(model_name)  # downloaded once, then cached locally

    def embed_passages(self, texts: list[str]) -> list[np.ndarray]:
        """For documents stored in the knowledge base."""
        return list(self._model.passage_embed(texts))

    def embed_query(self, text: str) -> np.ndarray:
        """For a user question (BGE adds its query instruction)."""
        return next(iter(self._model.query_embed([text])))
