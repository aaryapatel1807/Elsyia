"""Verify neural Ollama embeddings and semantic memory retrieval."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "true"
        os.environ["MEMORY_EMBEDDING_PROVIDER"] = "ollama"
        os.environ["MEMORY_EMBEDDING_MODEL"] = "nomic-embed-text"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")

        from app.services.memory import get_memory_store
        from app.services.memory.embeddings import neural_embed_text

        vector = neural_embed_text("Aarya prefers concise spoken answers.")
        if vector is None:
            print("SKIP: Ollama neural embedding model is unavailable; lexical/local fallback remains active")
            return
        assert len(vector) > 256, f"unexpected embedding dimensions: {len(vector)}"

        store = get_memory_store()
        store.save("Aarya prefers concise spoken answers.", category="preference")
        matches = store.search("What brief voice replies should I give?")
        assert matches, "neural semantic retrieval returned no match"
        assert "concise spoken answers" in matches[0].content

        print(f"neural_embedding_dimensions={len(vector)}")
        print("neural semantic RAG checks passed")


if __name__ == "__main__":
    main()
