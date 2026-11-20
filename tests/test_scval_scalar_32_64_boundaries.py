"""Focused offline checks for the Protocol 28 32-bit and 64-bit ScVal endpoints.

Issue #505 adds the missing opposite endpoints for i32, i64, u32 and u64, plus
zero and maximum coverage for the timepoint and duration arms. The timepoint
and duration extremes test the XDR integer representation only; they are not
claims that those timestamps or durations are useful ledger values.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK = REPO_ROOT / "protocol-28"
CODEC_PATH = REPO_ROOT / "tests" / "scval_xdr.py"

_spec = importlib.util.spec_from_file_location("scval_xdr", CODEC_PATH)
assert _spec is not None and _spec.loader is not None
scval_xdr = importlib.util.module_from_spec(_spec)
sys.modules["scval_xdr"] = scval_xdr
_spec.loader.exec_module(scval_xdr)

FIXTURES = {
    "p28-xdr-scval-i32-max": (
        "xdr/scval/p28-xdr-scval-i32-max.toml",
        "i32",
        (1 << 31) - 1,
    ),
    "p28-xdr-scval-i64-max": (
        "xdr/scval/p28-xdr-scval-i64-max.toml",
        "i64",
        (1 << 63) - 1,
    ),
    "p28-xdr-scval-u32-zero": (
        "xdr/scval/p28-xdr-scval-u32-zero.toml",
        "u32",
        0,
    ),
    "p28-xdr-scval-u64-zero": (
        "xdr/scval/p28-xdr-scval-u64-zero.toml",
        "u64",
        0,
    ),
    "p28-xdr-scval-timepoint-zero": (
        "xdr/scval/p28-xdr-scval-timepoint-zero.toml",
        "timepoint",
        0,
    ),
    "p28-xdr-scval-timepoint-max": (
        "xdr/scval/p28-xdr-scval-timepoint-max.toml",
        "timepoint",
        (1 << 64) - 1,
    ),
    "p28-xdr-scval-duration-zero": (
        "xdr/scval/p28-xdr-scval-duration-zero.toml",
        "duration",
        0,
    ),
    "p28-xdr-scval-duration-max": (
        "xdr/scval/p28-xdr-scval-duration-max.toml",
        "duration",
        (1 << 64) - 1,
    ),
}

EXTREME_TIME_IDS = {
    "p28-xdr-scval-timepoint-max",
    "p28-xdr-scval-duration-max",
}


class ScValScalarBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = {}
        for fixture_id, (relative, kind, value) in FIXTURES.items():
            path = PACK / relative
            text = path.read_text(encoding="utf-8")
            data = tomllib.loads(text)
            raw = base64.b64decode(data["value_base64"], validate=True)
            cls.loaded[fixture_id] = (path, text, data, raw, kind, value)

    def test_fixture_metadata_is_unique_and_pinned(self) -> None:
        self.assertEqual(len(FIXTURES), len(set(FIXTURES)))
        for fixture_id, (path, _text, data, _raw, _kind, _value) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertEqual(data["id"], fixture_id)
                self.assertEqual(data["protocol"], 28)
                self.assertEqual(data["surface"], "xdr")
                self.assertEqual(data["type"], "ScVal")
                self.assertEqual(data["kind"], "roundtrip")
                self.assertIn(
                    "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/",
                    data["source_reference"],
                )
                self.assertTrue(path.is_file())

    def test_headers_explain_how_expected_bytes_were_obtained(self) -> None:
        for fixture_id, (_path, text, _data, _raw, _kind, _value) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertIn("stellar-xdr 28.0.1", text)
                self.assertIn("to_xdr_base64(Limits::none())", text)
                self.assertIn("generated 2026-11-20 (UTC)", text)

    def test_endpoints_decode_to_the_expected_boundary_values(self) -> None:
        for fixture_id, (_path, _text, _data, raw, kind, value) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                decoded = scval_xdr.decode(raw)
                self.assertEqual(decoded, (kind, value))
                self.assertEqual(scval_xdr.encode(decoded), raw)
                self.assertEqual(scval_xdr.to_json(decoded), {"type": kind, "value": value})

    def test_signed_and_unsigned_widths_have_the_expected_payload_size(self) -> None:
        for fixture_id, width in (
            ("p28-xdr-scval-i32-max", 4),
            ("p28-xdr-scval-u32-zero", 4),
            ("p28-xdr-scval-i64-max", 8),
            ("p28-xdr-scval-u64-zero", 8),
            ("p28-xdr-scval-timepoint-zero", 8),
            ("p28-xdr-scval-timepoint-max", 8),
            ("p28-xdr-scval-duration-zero", 8),
            ("p28-xdr-scval-duration-max", 8),
        ):
            with self.subTest(fixture_id=fixture_id):
                self.assertEqual(len(self.loaded[fixture_id][3]), 4 + width)

    def test_time_extremes_are_documented_as_representation_tests_only(self) -> None:
        for fixture_id in EXTREME_TIME_IDS:
            with self.subTest(fixture_id=fixture_id):
                text = self.loaded[fixture_id][1]
                self.assertIn("XDR integer representation only", text)
                self.assertNotIn("valid ledger value", text.split("XDR integer representation only", 1)[0].lower())

    def test_evidence_records_bind_the_fixture_bytes(self) -> None:
        for fixture_id, (path, _text, _data, _raw, _kind, _value) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                record_path = PACK / "evidence" / "records" / f"{fixture_id}.json"
                record = json.loads(record_path.read_text(encoding="utf-8"))
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["outcome"], "matched")
                self.assertEqual(
                    record["fixtureSha256"],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
