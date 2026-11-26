"""Hostile input and verifier conformance tests for tools/release/run_records.py (issue #667).

Covers validation against schemas/run-record-v1.schema.json and
tools/release/run_records.py, including minimal and full valid records,
hostile numeric/duration/count fields, clock skew and malformed timestamps,
verifier metadata validation, evidenceRef path checks, and fail-closed loading.

Stdlib only: the CI ``validate`` job runs ``unittest discover`` on a bare
interpreter.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))
import pack_support as support  # noqa: E402

schema_validator = support.load_tool(
    "canary_jsonschema_lite", "tools/validate/jsonschema_lite.py"
)
run_records = support.load_tool("canary_run_records", "tools/release/run_records.py")

SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "run-record-v1.schema.json").read_text(encoding="utf-8")
)

FIXED_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
VALID_DIGEST = "sha256:" + "ab" * 32

MINIMAL_RECORD = {
    "runRecordVersion": 1,
    "engineVersion": "0.2.0",
    "packDigest": VALID_DIGEST,
    "checkedAt": "2026-10-22T11:55:00Z",
    "verifier": {"name": "protocol-canary-ci", "version": "0.2.0"},
    "outcome": "passed",
}

FULL_RECORD = {
    **MINIMAL_RECORD,
    "outcome": "failed",
    "evidenceRef": "protocol-28/evidence/records/p28-xdr-a.json",
}


class ValidRunRecordTests(unittest.TestCase):
    def test_minimal_and_full_records_conform_to_schema_and_reader(self) -> None:
        for name, template in (("minimal", MINIMAL_RECORD), ("full", FULL_RECORD)):
            with self.subTest(record=name):
                record = copy.deepcopy(template)
                self.assertEqual(schema_validator.validate(record, SCHEMA), [])
                self.assertEqual(run_records.validate_run_record(record, now=FIXED_NOW), [])

    def test_valid_variants_with_fractional_seconds_zero_version_and_null_ref(self) -> None:
        variants = [
            {
                **MINIMAL_RECORD,
                "engineVersion": "0.0.0",
                "checkedAt": "2026-10-22T11:59:59.123456Z",
                "evidenceRef": None,
            },
            {
                **MINIMAL_RECORD,
                "engineVersion": "12.34.56",
                "checkedAt": "2026-10-22T12:00:00.999999999Z",
                "outcome": "failed",
            },
        ]
        for variant in variants:
            with self.subTest(variant=variant["engineVersion"]):
                self.assertEqual(schema_validator.validate(variant, SCHEMA), [])
                self.assertEqual(run_records.validate_run_record(variant, now=FIXED_NOW), [])


class HostileRunRecordValidationTests(unittest.TestCase):
    def assert_rejected_by_both(self, record: dict, expected_substring: str | None = None) -> None:
        schema_errors = schema_validator.validate(record, SCHEMA)
        reader_problems = run_records.validate_run_record(record, now=FIXED_NOW)
        self.assertTrue(schema_errors, f"expected schema rejection for {record!r}")
        self.assertTrue(reader_problems, f"expected reader rejection for {record!r}")
        if expected_substring is not None:
            self.assertTrue(
                any(expected_substring in problem for problem in reader_problems),
                f"expected {expected_substring!r} in {reader_problems!r}",
            )

    def test_rejects_negative_durations_and_non_integer_or_unexpected_counts(self) -> None:
        hostile_payloads = [
            ("duration", -1, "duration"),
            ("duration", -0.5, "duration"),
            ("durationMs", -100, "durationMs"),
            ("passed", "not-an-int", "passed"),
            ("failed", 1.5, "failed"),
            ("skipped", True, "skipped"),
            ("counts", {"passed": "0", "failed": -1}, "counts"),
        ]
        for key, value, hint in hostile_payloads:
            with self.subTest(key=key, value=value):
                record = copy.deepcopy(MINIMAL_RECORD)
                record[key] = value
                self.assert_rejected_by_both(record, hint)

    def test_rejects_unexpected_additional_properties(self) -> None:
        record = copy.deepcopy(FULL_RECORD)
        record["unexpectedProperty"] = "evil"
        self.assert_rejected_by_both(record, "unknown field 'unexpectedProperty'")

    def test_rejects_invalid_run_record_version_types_and_values(self) -> None:
        for bad_version in (0, 2, -1, 1.0, "1", True, False, None):
            with self.subTest(runRecordVersion=bad_version):
                record = copy.deepcopy(MINIMAL_RECORD)
                record["runRecordVersion"] = bad_version
                self.assert_rejected_by_both(record, "runRecordVersion")

    def test_rejects_invalid_engine_version_and_pack_digest(self) -> None:
        for bad_engine in ("^0.2.0", ">=0.2.0", "0.2.x", "01.2.3", "1.2", "1.2.3-rc1", 20):
            with self.subTest(engineVersion=bad_engine):
                record = copy.deepcopy(MINIMAL_RECORD)
                record["engineVersion"] = bad_engine
                self.assert_rejected_by_both(record, "engineVersion")

        for bad_digest in (
            "ab" * 32,
            "sha256:" + "AB" * 32,
            "sha256:" + "ab" * 31,
            "sha256:" + "g" * 64,
            12345,
        ):
            with self.subTest(packDigest=bad_digest):
                record = copy.deepcopy(MINIMAL_RECORD)
                record["packDigest"] = bad_digest
                self.assert_rejected_by_both(record, "packDigest")

    def test_rejects_missing_required_fields(self) -> None:
        for field in run_records.REQUIRED_FIELDS:
            with self.subTest(missing=field):
                record = copy.deepcopy(MINIMAL_RECORD)
                del record[field]
                self.assert_rejected_by_both(record, f"missing required field {field!r}")


class TimestampAndClockSkewTests(unittest.TestCase):
    def test_clock_skew_boundary_accepts_five_minutes_and_rejects_beyond(self) -> None:
        at_boundary = (FIXED_NOW + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        over_boundary = (FIXED_NOW + timedelta(minutes=5, seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        distant_future = "2099-01-01T00:00:00Z"

        valid_skew = {**MINIMAL_RECORD, "checkedAt": at_boundary}
        self.assertEqual(run_records.validate_run_record(valid_skew, now=FIXED_NOW), [])

        for bad_future in (over_boundary, distant_future):
            with self.subTest(checkedAt=bad_future):
                invalid = {**MINIMAL_RECORD, "checkedAt": bad_future}
                problems = run_records.validate_run_record(invalid, now=FIXED_NOW)
                self.assertTrue(problems)
                self.assertTrue(any("in the future" in p for p in problems), problems)

    def test_rejects_invalid_iso8601_and_nonexistent_dates(self) -> None:
        bad_syntax = (
            "2026-10-22",
            "2026-10-22 12:00:00Z",
            "2026-10-22T12:00:00",
            "2026-10-22T12:00:00+00:00",
            "2026-10-22T12:00:00z",
            "2026-10-22T12:00:00.Z",
            "not-a-timestamp",
            20261022,
            None,
        )
        for bad in bad_syntax:
            with self.subTest(checkedAt=bad):
                record = {**MINIMAL_RECORD, "checkedAt": bad}
                self.assertTrue(schema_validator.validate(record, SCHEMA))
                problems = run_records.validate_run_record(record, now=FIXED_NOW)
                self.assertTrue(any("RFC 3339" in p for p in problems), problems)

        impossible_dates = (
            "2026-02-29T00:00:00Z",
            "2026-13-01T00:00:00Z",
            "2026-10-32T00:00:00Z",
            "2026-10-22T24:00:00Z",
        )
        for bad_date in impossible_dates:
            with self.subTest(impossible=bad_date):
                record = {**MINIMAL_RECORD, "checkedAt": bad_date}
                problems = run_records.validate_run_record(record, now=FIXED_NOW)
                self.assertTrue(any("not a real date" in p for p in problems), problems)


class VerifierAndPathTests(unittest.TestCase):
    def test_rejects_verifier_missing_name_or_version_or_with_empty_values(self) -> None:
        bad_verifiers = [
            ({}, "verifier.name", True),
            ({"name": "ci"}, "verifier.version", True),
            ({"version": "1.0.0"}, "verifier.name", True),
            ({"name": "", "version": "1.0.0"}, "verifier.name", True),
            ({"name": "   ", "version": "1.0.0"}, "verifier.name", False),
            ({"name": "ci", "version": ""}, "verifier.version", True),
            ({"name": "ci", "version": "\t\n"}, "verifier.version", False),
            ({"name": 123, "version": "1.0.0"}, "verifier.name", True),
            ({"name": "ci", "version": None}, "verifier.version", True),
            ("protocol-canary-ci", "verifier must be an object", True),
            (["ci", "1.0.0"], "verifier must be an object", True),
            (None, "verifier must be an object", True),
        ]
        for bad_verifier, expected_msg, rejected_by_schema in bad_verifiers:
            with self.subTest(verifier=bad_verifier):
                record = {**MINIMAL_RECORD, "verifier": bad_verifier}
                problems = run_records.validate_run_record(record, now=FIXED_NOW)
                self.assertTrue(problems)
                self.assertTrue(
                    any(expected_msg in p for p in problems),
                    f"expected {expected_msg!r} in {problems!r}",
                )
                if rejected_by_schema:
                    self.assertTrue(schema_validator.validate(record, SCHEMA))

    def test_rejects_verifier_with_unexpected_extra_property(self) -> None:
        record = {
            **MINIMAL_RECORD,
            "verifier": {"name": "ci", "version": "1.0.0", "extra": "bad"},
        }
        self.assertTrue(schema_validator.validate(record, SCHEMA))
        problems = run_records.validate_run_record(record, now=FIXED_NOW)
        self.assertTrue(any("unknown field 'extra' in verifier" in p for p in problems), problems)

    def test_rejects_unsafe_or_empty_evidence_ref(self) -> None:
        for bad_ref in (
            "",
            "   ",
            "/absolute/path.json",
            "../escape.json",
            "evidence/../escape.json",
            "./dot.json",
            "evidence\\windows.json",
            "a//b.json",
        ):
            with self.subTest(evidenceRef=bad_ref):
                record = {**MINIMAL_RECORD, "evidenceRef": bad_ref}
                problems = run_records.validate_run_record(record, now=FIXED_NOW)
                self.assertTrue(problems)
                self.assertTrue(any("evidenceRef" in p for p in problems), problems)


class RunRecordLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="run-records-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_load_run_records_sorts_valid_records_and_lookup_helpers_match_exact_pair(self) -> None:
        r1 = {**MINIMAL_RECORD, "engineVersion": "0.2.0"}
        r2 = {
            **FULL_RECORD,
            "engineVersion": "0.3.0",
            "packDigest": "sha256:" + "cd" * 32,
        }
        (self.root / "b.json").write_text(json.dumps(r2), encoding="utf-8")
        (self.root / "a.json").write_text(json.dumps(r1), encoding="utf-8")

        loaded = run_records.load_run_records(self.root, now=FIXED_NOW)
        self.assertEqual([r["engineVersion"] for r in loaded], ["0.2.0", "0.3.0"])
        self.assertEqual(run_records.records_for_engine(loaded, "0.2.0"), [r1])
        self.assertEqual(run_records.find_record(loaded, "0.3.0", r2["packDigest"]), r2)
        self.assertIsNone(run_records.find_record(loaded, "0.2.0", r2["packDigest"]))

    def test_load_run_records_fails_closed_on_any_invalid_or_missing_dir(self) -> None:
        with self.assertRaisesRegex(run_records.RunRecordError, "directory not found"):
            run_records.load_run_records(self.root / "missing")

        (self.root / "01-valid.json").write_text(json.dumps(MINIMAL_RECORD), encoding="utf-8")
        (self.root / "02-hostile.json").write_text(
            json.dumps({**MINIMAL_RECORD, "duration": -5}), encoding="utf-8"
        )
        with self.assertRaisesRegex(run_records.RunRecordError, "not a valid run record"):
            run_records.load_run_records(self.root, now=FIXED_NOW)

        (self.root / "02-hostile.json").write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(run_records.RunRecordError, "not valid JSON"):
            run_records.load_run_records(self.root, now=FIXED_NOW)


if __name__ == "__main__":
    unittest.main()
