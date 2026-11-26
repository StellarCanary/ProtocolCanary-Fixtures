"""Tests for the schema/validator synchronization check.

Run with: python3 -m unittest tests/test_schema_sync.py
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import pathlib
import subprocess
import sys
import unittest
import unittest.mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_SYNC_PATH = REPO_ROOT / "tools" / "validate" / "schema_sync.py"

_spec = importlib.util.spec_from_file_location("schema_sync_under_test", SCHEMA_SYNC_PATH)
schema_sync = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(schema_sync)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the same schema-sync entry point used by CI."""
    return subprocess.run(
        [sys.executable, str(SCHEMA_SYNC_PATH), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        check=False,
    )


def run_main_with_schema(schema: dict) -> tuple[int, str, str]:
    """Run ``main`` against an in-memory schema without changing repository files."""
    validator = schema_sync.load_validator()
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        unittest.mock.patch.object(schema_sync, "load_schema", return_value=schema),
        unittest.mock.patch.object(schema_sync, "load_validator", return_value=validator),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        exit_code = schema_sync.main([])
    return exit_code, stdout.getvalue(), stderr.getvalue()


class SchemaSyncCliTests(unittest.TestCase):
    def test_current_schema_and_validator_are_synchronized(self) -> None:
        result = run_cli()

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "OK: schemas/fixture-v1.schema.json matches tools/validate/validate.py",
            result.stdout,
        )
        self.assertEqual(result.stderr, "")

    def test_help_prints_usage_and_exits_zero(self) -> None:
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
        self.assertIn("schema_sync.py", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_unknown_flag_prints_usage_to_stderr_and_exits_two(self) -> None:
        result = run_cli("--unexpected")

        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertEqual(result.stdout, "")


class SchemaSyncDriftTests(unittest.TestCase):
    def test_enum_drift_reports_missing_and_extra_values(self) -> None:
        schema = copy.deepcopy(schema_sync.load_schema())
        schema["properties"]["surface"]["enum"].remove("rpc")
        schema["properties"]["required_capabilities"]["items"]["enum"].append(
            "stale-capability"
        )

        exit_code, stdout, stderr = run_main_with_schema(schema)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("surface enum", stderr)
        self.assertIn("schema is missing ['rpc']", stderr)
        self.assertIn("required_capabilities enum", stderr)
        self.assertIn("schema lists unsupported ['stale-capability']", stderr)
        self.assertIn("FAILED: 2 schema/validator drift error(s)", stderr)

    def test_missing_required_fields_are_reported(self) -> None:
        schema = copy.deepcopy(schema_sync.load_schema())
        schema["required"].remove("description")
        xdr = schema_sync.surface_block(schema, "xdr")
        assert xdr is not None
        xdr["required"].remove("value_base64")

        exit_code, stdout, stderr = run_main_with_schema(schema)

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("top-level required fields", stderr)
        self.assertIn("schema is missing ['description']", stderr)
        self.assertIn("xdr required fields", stderr)
        self.assertIn("schema is missing ['value_base64']", stderr)
        self.assertIn("FAILED: 2 schema/validator drift error(s)", stderr)


if __name__ == "__main__":
    unittest.main()
