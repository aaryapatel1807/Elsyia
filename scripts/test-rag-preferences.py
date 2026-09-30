"""Phase 2 semantic retrieval and preference extraction checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "true"
        os.environ["ENABLE_PREFERENCE_EXTRACTION"] = "true"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")

        from app.services.memory import get_memory_store
        from app.services.memory.preferences import (
            extract_candidates,
            persist_candidates,
        )

        store = get_memory_store()
        store.save("Aarya prefers concise spoken answers.", category="preference")
        matches = store.search("What short voice replies do you prefer?")
        assert matches, "paraphrased query did not retrieve the memory"
        assert "concise spoken answers" in matches[0].content

        candidates = extract_candidates("I prefer dark mode for the desktop app.")
        assert len(candidates) == 1
        assert candidates[0].category == "preference"
        assert persist_candidates(candidates) == 1
        assert persist_candidates(candidates) == 0

        assert extract_candidates("My password is swordfish") == []
        assert extract_candidates("What do you prefer?") == []

    print("rag and preference checks passed")


if __name__ == "__main__":
    asyncio.run(main())
