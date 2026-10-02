"""Regression checks for the local factuality guard."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.v1.chat import _unsupported_realtime_response  # noqa: E402


class AccuracyGuardTests(unittest.TestCase):
    def test_live_data_is_not_guessed(self) -> None:
        response = _unsupported_realtime_response("What is the current weather in London right now?")
        self.assertIsNotNone(response)
        self.assertIn("will not guess", response or "")

    def test_ordinary_factual_questions_are_not_blocked(self) -> None:
        self.assertIsNone(_unsupported_realtime_response("What is the capital of Australia?"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
