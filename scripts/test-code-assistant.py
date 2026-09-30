"""Phase 7 read-only repository analysis checks."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        (root / "src").mkdir()
        (root / "node_modules" / "ignored").mkdir(parents=True)
        (root / "data").mkdir()
        (root / "src" / "main.py").write_text(
            "class Widget:\n    pass\n\ndef needle(value: str) -> str:\n    return value\n",
            encoding="utf-8",
        )
        (root / "src" / "app.ts").write_text("export function renderWidget() { return true; }\n", encoding="utf-8")
        (root / "node_modules" / "ignored" / "hidden.js").write_text("needle hidden", encoding="utf-8")
        (root / "binary.bin").write_bytes(b"\x00\x01needle")

        os.environ["CODE_ENABLED"] = "true"
        os.environ["CODE_REPOSITORY_ROOTS"] = str(root)
        os.environ["CODE_INDEX_CACHE_PATH"] = "data/code_index.json"
        os.environ["CODE_MAX_FILES"] = "100"
        os.environ["CODE_MAX_RESULTS"] = "20"

        from app.services.code import CodePolicyError, repository_indexer
        from app.services.tools.intent import route_intent

        assert route_intent("analyze repository").tool_name == "analyze_code_repository"
        assert route_intent("index repository").tool_name == "index_code_repository"
        assert route_intent("search code for Widget").arguments == {"query": "Widget", "mode": "text"}

        index = await repository_indexer.build(str(root))
        paths = {record["path"] for record in index.files}
        assert "src/main.py" in paths
        assert "src/app.ts" in paths
        assert not any("node_modules" in path for path in paths)
        assert not any(path.endswith("binary.bin") for path in paths)
        python_record = next(record for record in index.files if record["path"] == "src/main.py")
        assert "Widget" in python_record["symbols"]
        assert "needle" in python_record["symbols"]

        searched = await repository_indexer.search("needle", mode="text", raw_root=str(root))
        assert searched["matches"]
        assert all("node_modules" not in match["path"] for match in searched["matches"])

        symbol_matches = await repository_indexer.search("Widget", mode="symbol", raw_root=str(root))
        assert symbol_matches["matches"]

        analysis = await repository_indexer.analyze(str(root))
        assert analysis["file_count"] == 2
        assert analysis["languages"]["Python"] == 1
        assert analysis["languages"]["TypeScript"] == 1
        assert analysis["symbol_count"] >= 3

        cache_path = root / "data" / "code_index.json"
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        assert "files" in cached
        assert "needle hidden" not in cache_path.read_text(encoding="utf-8")

        try:
            await repository_indexer.analyze(str(root.parent / "outside"))
        except CodePolicyError:
            pass
        else:
            raise AssertionError("repository policy allowed an outside root")

        import httpx
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            analyzed = await client.post("/api/v1/code/analyze", json={"root": str(root)})
            assert analyzed.status_code == 200, analyzed.text
            assert analyzed.json()["result"]["file_count"] == 2
            searched_api = await client.post(
                "/api/v1/code/search",
                json={"root": str(root), "query": "renderWidget", "mode": "symbol"},
            )
            assert searched_api.status_code == 200, searched_api.text
            assert searched_api.json()["result"]["matches"]

    print("code assistant foundation checks passed")


if __name__ == "__main__":
    asyncio.run(main())
