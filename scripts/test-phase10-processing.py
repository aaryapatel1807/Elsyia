"""Regression tests for Phase 10 local attachment processing."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
import sys

sys.path.insert(0, str(BACKEND))

from app.core import get_settings  # noqa: E402
from app.services.input import AttachmentStore, InputValidationError, process_one_job  # noqa: E402
import app.services.input.manager as input_manager  # noqa: E402
import app.services.memory.store as memory_store_module  # noqa: E402
import app.services.input.processor as processor_module  # noqa: E402


class FakeProvider:
    async def generate(self, messages, temperature=0.2, max_tokens=384):
        yield "This file documents the local project architecture and testing workflow."


class SecretProvider:
    async def generate(self, messages, temperature=0.2, max_tokens=384):
        yield "The document contains an API key and should not become memory."


class Phase10ProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.safe = self.root / "safe"
        self.safe.mkdir()
        self.settings = get_settings()
        self.settings.INPUT_ENABLED = True
        self.settings.INPUT_PROCESSING_ENABLED = True
        self.settings.INPUT_PROCESSING_AUTO_SUMMARY = True
        self.settings.INPUT_PROCESSING_ALLOW_CLOUD = False
        self.settings.INPUT_SAFE_ROOTS = str(self.safe)
        self.settings.INPUT_ATTACHMENT_DIR = str(self.root / "attachments")
        self.settings.INPUT_ALLOWED_EXTENSIONS = ".txt,.png"
        self.settings.INPUT_MAX_FILE_BYTES = 10_000
        self.settings.INPUT_MAX_TOTAL_BYTES = 20_000
        self.settings.INPUT_MAX_ATTACHMENTS = 100
        self.settings.INPUT_PROCESSING_MAX_TEXT_CHARS = 100
        self.settings.INPUT_PROCESSING_MAX_SUMMARY_CHARS = 200
        self.settings.INPUT_PROCESSING_MAX_MEMORY_PROPOSALS = 1
        self.settings.DEFAULT_LLM_PROVIDER = "ollama"
        self.settings.MEMORY_DB_PATH = str(self.root / "memory.db")
        self.settings.MEMORY_MAX_CONTENT_LENGTH = 1000
        self.store = AttachmentStore()
        input_manager._store = self.store
        memory_store_module._memory_store = None
        self.original_provider_factory = processor_module.create_llm_provider
        processor_module.create_llm_provider = lambda provider: FakeProvider()

    def tearDown(self) -> None:
        processor_module.create_llm_provider = self.original_provider_factory
        input_manager._store = None
        memory_store_module._memory_store = None
        self.temp.cleanup()

    def _write(self, name: str, content: str) -> Path:
        path = self.safe / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_ingest_queues_and_processes_text_with_pending_memory(self) -> None:
        source = self._write("architecture.txt", "The project uses a local SQLite database.")
        event = self.store.ingest_files([str(source)])[0]
        self.assertIsNotNone(event.processing_job)
        claimed = self.store.next_queued_processing_job()
        self.assertIsNotNone(claimed)

        completed = asyncio.run(process_one_job(self.store, claimed))
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, "completed")
        self.assertIn("local project architecture", completed.summary or "")
        self.assertEqual(len(completed.memory_proposal_ids), 1)

        memories = __import__("app.services.memory", fromlist=["get_memory_store"]).get_memory_store().list(
            include_pending=True
        )
        self.assertEqual(len(memories), 1)
        self.assertFalse(memories[0].approved)
        self.assertEqual(memories[0].source, "attachment")

    def test_text_is_bounded_and_marked_truncated(self) -> None:
        source = self._write("long.txt", "x" * 500)
        event = self.store.ingest_files([str(source)])[0]
        claimed = self.store.next_queued_processing_job()
        asyncio.run(process_one_job(self.store, claimed))
        job = self.store.get_latest_processing_job(event.attachment_token)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.extracted_chars, 100)
        self.assertTrue(job.truncated)

    def test_secret_like_summary_does_not_create_memory(self) -> None:
        processor_module.create_llm_provider = lambda provider: SecretProvider()
        source = self._write("secret.txt", "not a credential value")
        event = self.store.ingest_files([str(source)])[0]
        claimed = self.store.next_queued_processing_job()
        asyncio.run(process_one_job(self.store, claimed))
        job = self.store.get_latest_processing_job(event.attachment_token)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.memory_proposal_ids, ())

    def test_unsupported_file_finishes_as_failed_without_model_call(self) -> None:
        source = self.safe / "image.png"
        source.write_bytes(b"not an actual image")
        event = self.store.ingest_files([str(source)])[0]
        claimed = self.store.next_queued_processing_job()
        asyncio.run(process_one_job(self.store, claimed))
        job = self.store.get_latest_processing_job(event.attachment_token)
        self.assertEqual(job.status, "failed")
        self.assertIn("no local text processor", job.error or "")

    def test_cloud_provider_is_blocked_by_default(self) -> None:
        self.settings.DEFAULT_LLM_PROVIDER = "openrouter"
        source = self._write("cloud.txt", "private local content")
        event = self.store.ingest_files([str(source)])[0]
        claimed = self.store.next_queued_processing_job()
        asyncio.run(process_one_job(self.store, claimed))
        job = self.store.get_latest_processing_job(event.attachment_token)
        self.assertEqual(job.status, "failed")
        self.assertIn("restricted to local Ollama", job.error or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
