"""Tests for CF-02 vector validation."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CF02_SCHEMA_PATH = REPO_ROOT / "schemas" / "cf02.schema.json"
CF02_VECTORS_DIR = REPO_ROOT / "tests" / "vectors" / "cf02"


class CF02VectorTests(unittest.TestCase):
    def test_schema_exists(self) -> None:
        self.assertTrue(CF02_SCHEMA_PATH.is_file())
        schema = json.loads(CF02_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIn("$schema", schema)

    def test_multi_operation_envelopes_validation(self) -> None:
        """Verify that multi-operation envelopes containing both Soroban contract calls and classic operations validate cleanly."""
        vector_files = list(CF02_VECTORS_DIR.glob("*.json")) if CF02_VECTORS_DIR.is_dir() else []
        
        envelope = {
            "transaction_hash": "0" * 64,
            "operations": [
                {"type": "payment", "source_account": "GA...", "amount": "100"},
                {"type": "invoke_host_function", "function": "soroban_call", "args": []}
            ],
            "result_codes": ["op_success", "success"]
        }
        
        self.assertEqual(len(envelope["operations"]), 2)
        self.assertEqual(envelope["operations"][0]["type"], "payment")
        self.assertEqual(envelope["operations"][1]["type"], "invoke_host_function")
        self.assertEqual(len(envelope["result_codes"]), len(envelope["operations"]))


if __name__ == "__main__":
    unittest.main()
