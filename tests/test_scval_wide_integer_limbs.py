"""Focused offline checks for the Protocol 28 wide-integer limb boundaries.

Issue #506 adds 2^64 for u128/u256 and -1 for i128/i256. The unsigned values
place a non-zero word in a specific high limb with all lower limbs zero; the
signed -1 values require all-ones sign extension across every limb.
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
    "p28-xdr-scval-u128-u64-boundary": (
        "xdr/scval/p28-xdr-scval-u128-u64-boundary.toml",
        "u128",
        1 << 64,
    ),
    "p28-xdr-scval-i128-negative-one": (
        "xdr/scval/p28-xdr-scval-i128-negative-one.toml",
        "i128",
        -1,
    ),
    "p28-xdr-scval-u256-u64-boundary": (
        "xdr/scval/p28-xdr-scval-u256-u64-boundary.toml",
        "u256",
        1 << 64,
    ),
    "p28-xdr-scval-i256-negative-one": (
        "xdr/scval/p28-xdr-scval-i256-negative-one.toml",
        "i256",
        -1,
    ),
}

U64 = 1 << 64


def limbs(raw: bytes, width: int) -> list[int]:
    return [int.from_bytes(raw[4 + index * 8 : 12 + index * 8], "big") for index in range(width)]


class ScValWideIntegerLimbTests(unittest.TestCase):
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

    def test_values_decode_and_round_trip(self) -> None:
        for fixture_id, (_path, _text, _data, raw, kind, value) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                decoded = scval_xdr.decode(raw)
                self.assertEqual(decoded, (kind, value))
                self.assertEqual(scval_xdr.encode(decoded), raw)
                self.assertEqual(scval_xdr.to_json(decoded), {"type": kind, "value": value})

    def test_u128_low_limb_carry_sets_only_the_high_limb(self) -> None:
        raw = self.loaded["p28-xdr-scval-u128-u64-boundary"][3]
        self.assertEqual(limbs(raw, 2), [1, 0])

    def test_i128_negative_one_sign_extends_both_limbs(self) -> None:
        raw = self.loaded["p28-xdr-scval-i128-negative-one"][3]
        self.assertEqual(limbs(raw, 2), [U64 - 1, U64 - 1])
        self.assertEqual(raw[4:], b"\xff" * 16)

    def test_u256_low_limb_carry_sets_only_the_third_limb(self) -> None:
        raw = self.loaded["p28-xdr-scval-u256-u64-boundary"][3]
        self.assertEqual(limbs(raw, 4), [0, 0, 1, 0])

    def test_i256_negative_one_sign_extends_all_four_limbs(self) -> None:
        raw = self.loaded["p28-xdr-scval-i256-negative-one"][3]
        self.assertEqual(limbs(raw, 4), [U64 - 1] * 4)
        self.assertEqual(raw[4:], b"\xff" * 32)

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
