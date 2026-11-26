"""Boundary and mocked-clock tests for tools/evidence/freshness.py (issue #669).

Verifies exact freshness window thresholds (<30d fresh, 30-90d aging, >90d stale),
clock-skew and future timestamp handling, diagnostic output, and --strict behavior
with deterministic mocked UTC time.

Stdlib only: the CI ``validate`` job runs ``unittest discover`` on a bare
interpreter.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.evidence import freshness  # noqa: E402

MOCK_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)


def _mock_datetime_class(fixed_now: datetime):
    """Return a datetime subclass whose ``now(tz)`` returns ``fixed_now``."""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now.astimezone(tz)

    return _FixedDatetime


class FreshnessBoundaryTests(unittest.TestCase):
    def test_exact_classification_thresholds(self) -> None:
        self.assertEqual(freshness.classify_freshness(0), "fresh")
        self.assertEqual(freshness.classify_freshness(29), "fresh")
        self.assertEqual(freshness.classify_freshness(30), "aging")
        self.assertEqual(freshness.classify_freshness(90), "aging")
        self.assertEqual(freshness.classify_freshness(91), "stale")

    def test_record_freshness_at_exact_date_boundaries(self) -> None:
        path = Path("record.json")
        # MOCK_NOW is 2026-10-22T12:00:00Z; age_days is computed from UTC dates.
        cases = [
            ("2026-10-22T12:00:00Z", 0, "fresh"),
            ("2026-10-22T00:00:00Z", 0, "fresh"),
            ("2026-09-23T23:59:59Z", 29, "fresh"),
            ("2026-09-23T00:00:00Z", 29, "fresh"),
            ("2026-09-22T23:59:59Z", 30, "aging"),
            ("2026-09-22T00:00:00Z", 30, "aging"),
            ("2026-07-24T23:59:59Z", 90, "aging"),
            ("2026-07-24T00:00:00Z", 90, "aging"),
            ("2026-07-23T23:59:59Z", 91, "stale"),
            ("2026-07-23T00:00:00Z", 91, "stale"),
        ]
        for checked_at, expected_days, expected_status in cases:
            with self.subTest(checkedAt=checked_at):
                result = freshness.calculate_record_freshness(
                    path,
                    {"fixtureId": "p28-boundary", "checkedAt": checked_at},
                    now=MOCK_NOW,
                )
                self.assertEqual(result.age_days, expected_days)
                self.assertEqual(result.status, expected_status)

    def test_slight_past_skew_and_exact_instant_pass_without_warnings(self) -> None:
        for delta in (timedelta(0), timedelta(seconds=1), timedelta(minutes=5)):
            instant = (MOCK_NOW - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
            with self.subTest(checkedAt=instant):
                result = freshness.calculate_record_freshness(
                    Path("skew.json"),
                    {"fixtureId": "p28-skew-ok", "checkedAt": instant},
                    now=MOCK_NOW,
                )
                self.assertEqual(result.age_days, 0)
                self.assertEqual(result.status, "fresh")

    def test_future_timestamps_are_rejected_with_clear_diagnostics(self) -> None:
        for delta in (
            timedelta(microseconds=1),
            timedelta(seconds=1),
            timedelta(minutes=5, seconds=1),
            timedelta(days=365),
        ):
            future_dt = MOCK_NOW + delta
            if future_dt.microsecond:
                future_str = future_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            else:
                future_str = future_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            with self.subTest(checkedAt=future_str):
                with self.assertRaises(freshness.FreshnessFormatError) as ctx:
                    freshness.parse_checked_at(future_str, now=MOCK_NOW)
                message = str(ctx.exception)
                self.assertIn("future timestamp", message)
                self.assertIn(future_str, message)


class MockedClockCliAndScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="freshness-boundaries-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write_record(self, filename: str, fixture_id: str, checked_at: str) -> Path:
        path = self.root / filename
        path.write_text(
            json.dumps(
                {
                    "verificationVersion": 1,
                    "fixtureId": fixture_id,
                    "checkedAt": checked_at,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_mocked_clock_drives_scan_and_strict_mode_across_boundaries(self) -> None:
        self._write_record("fresh.json", "f-fresh-29d", "2026-09-23T00:00:00Z")
        self._write_record("aging.json", "f-aging-30d", "2026-09-22T23:59:59Z")
        self._write_record("aging_edge.json", "f-aging-90d", "2026-07-24T00:00:00Z")
        self._write_record("stale.json", "f-stale-91d", "2026-07-23T23:59:59Z")

        with patch.object(freshness, "datetime", _mock_datetime_class(MOCK_NOW)):
            results, errors = freshness.scan_freshness([self.root])
            self.assertEqual(errors, [])
            statuses = {item.fixture_id: item.status for item in results}
            self.assertEqual(
                statuses,
                {
                    "f-fresh-29d": "fresh",
                    "f-aging-30d": "aging",
                    "f-aging-90d": "aging",
                    "f-stale-91d": "stale",
                },
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                non_strict = freshness.main([str(self.root)])
            self.assertEqual(non_strict, 0)
            self.assertIn("Fresh: 1 | Aging: 2 | Stale: 1 | Errors: 0", stdout.getvalue())

            stdout_strict = io.StringIO()
            stderr_strict = io.StringIO()
            with contextlib.redirect_stdout(stdout_strict), contextlib.redirect_stderr(
                stderr_strict
            ):
                strict_code = freshness.main([str(self.root), "--strict"])
            self.assertEqual(strict_code, 1)
            self.assertIn("ERROR: --strict enabled and 1 stale record(s) found.", stderr_strict.getvalue())

    def test_mocked_clock_strict_passes_with_only_fresh_and_aging_records(self) -> None:
        self._write_record("fresh.json", "f-fresh", "2026-09-23T00:00:00Z")
        self._write_record("aging.json", "f-aging", "2026-07-24T00:00:00Z")

        with patch.object(freshness, "datetime", _mock_datetime_class(MOCK_NOW)):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = freshness.main([str(self.root), "--strict"])
            self.assertEqual(code, 0)
            self.assertIn("Fresh: 1 | Aging: 1 | Stale: 0 | Errors: 0", stdout.getvalue())

    def test_mocked_clock_reports_future_record_in_main_with_exit_code_one(self) -> None:
        self._write_record("future.json", "f-future", "2026-10-22T12:00:01Z")

        with patch.object(freshness, "datetime", _mock_datetime_class(MOCK_NOW)):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = freshness.main([str(self.root)])
            self.assertEqual(code, 1)
            self.assertIn("Errors: 1", stdout.getvalue())
            self.assertIn("future timestamp", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
