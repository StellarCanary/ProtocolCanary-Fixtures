"""Tests for tools/evidence/record_structural.py.

Run with: python3 -m unittest tests/test_record_structural.py
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import re
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD_STRUCTURAL_PATH = REPO_ROOT / "tools" / "evidence" / "record_structural.py"

_spec = importlib.util.spec_from_file_location("record_structural", RECORD_STRUCTURAL_PATH)
record_structural = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(record_structural)

VALID_FIXTURE = """
id = "p28-xdr-structural-example"
protocol = 28
surface = "xdr"
category = "cap-0083"
description = "synthetic structural-record test fixture"
source_reference = "CAP-0083"

type = "StellarValue"
kind = "decode-success"
value_base64 = "AAAAAA=="
""".lstrip()

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class StructuralRecordTests(unittest.TestCase):
    def write_fixture(
        self, pack: pathlib.Path, contents: str = VALID_FIXTURE
    ) -> pathlib.Path:
        fixture = pack / "xdr" / "p28-xdr-structural-example.toml"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(contents, encoding="utf-8")
        return fixture

    def test_valid_pack_generates_schema_compliant_record_with_exact_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = pathlib.Path(temporary) / "pack"
            output = pathlib.Path(temporary) / "records"
            fixture = self.write_fixture(pack)

            written, checked_at = record_structural.run(
                pack,
                output_dir=output,
                version="test-verifier",
            )

            self.assertEqual(written, [output / "p28-xdr-structural-example.json"])
            self.assertTrue(TIMESTAMP_PATTERN.fullmatch(checked_at), checked_at)
            record = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(
                record["fixtureSha256"],
                hashlib.sha256(fixture.read_bytes()).hexdigest(),
            )
            self.assertEqual(record["checkedAt"], checked_at)
            self.assertEqual(record["method"], "structural")
            self.assertEqual(record["verifier"]["version"], "test-verifier")
            self.assertEqual(record_structural.validate.validate_evidence(record), [])

    def test_date_only_checked_at_is_rejected_by_evidence_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = pathlib.Path(temporary) / "pack"
            output = pathlib.Path(temporary) / "records"
            self.write_fixture(pack)
            written, _ = record_structural.run(pack, output_dir=output, version="test-verifier")
            record = json.loads(written[0].read_text(encoding="utf-8"))
            record["checkedAt"] = "2026-09-02"

            problems = record_structural.validate.validate_evidence(record)

            self.assertTrue(
                any("checkedAt must be an RFC 3339 UTC instant" in problem for problem in problems),
                problems,
            )

    def test_invalid_fixture_prevents_all_record_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = pathlib.Path(temporary) / "pack"
            output = pathlib.Path(temporary) / "records"
            self.write_fixture(pack, VALID_FIXTURE.replace('kind = "decode-success"', "kind ="))

            with self.assertRaisesRegex(record_structural.RecordError, "does not validate"):
                record_structural.run(pack, output_dir=output, version="test-verifier")

            self.assertFalse(output.exists())

    def test_dry_run_calculates_timestamp_without_writing_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pack = pathlib.Path(temporary) / "pack"
            output = pathlib.Path(temporary) / "records"
            self.write_fixture(pack)

            written, checked_at = record_structural.run(
                pack,
                output_dir=output,
                version="test-verifier",
                dry_run=True,
            )

            self.assertEqual(written, [])
            self.assertTrue(TIMESTAMP_PATTERN.fullmatch(checked_at), checked_at)
            self.assertFalse(output.exists())

    def test_cli_output_dir_and_verifier_version_control_written_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            pack = root / "pack"
            output = root / "custom-records"
            self.write_fixture(pack)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = record_structural.main(
                    [
                        str(pack),
                        "--output-dir",
                        str(output),
                        "--verifier-version",
                        "cli-verifier",
                    ]
                )

            self.assertEqual(exit_code, 0)
            record_path = output / "p28-xdr-structural-example.json"
            self.assertTrue(record_path.is_file())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["verifier"]["version"], "cli-verifier")
            self.assertIn("wrote 1 record(s)", stdout.getvalue())

    def test_cli_dry_run_does_not_create_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            pack = root / "pack"
            output = root / "dry-run-records"
            self.write_fixture(pack)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = record_structural.main(
                    [str(pack), "--output-dir", str(output), "--dry-run"]
                )

            self.assertEqual(exit_code, 0)
            self.assertFalse(output.exists())
            self.assertIn("no record written (dry run at ", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
