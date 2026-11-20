"""Focused offline checks for the Protocol 28 null SCMap fixture (issue #504).

The pack already exercises a present-but-empty SCMap. This module pins the
distinct absent-pointer encoding and proves it is not collapsed onto the empty
map.
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

NULL_PATH = PACK / "xdr" / "scval-composite" / "p28-xdr-scval-map-null.toml"
EMPTY_PATH = PACK / "xdr" / "scval-composite" / "p28-xdr-scval-map-empty.toml"
FIXTURE_ID = "p28-xdr-scval-map-null"


class ScValMapNullFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.null_text = NULL_PATH.read_text(encoding="utf-8")
        cls.null_data = tomllib.loads(cls.null_text)
        cls.null_raw = base64.b64decode(cls.null_data["value_base64"], validate=True)
        cls.empty_data = tomllib.loads(EMPTY_PATH.read_text(encoding="utf-8"))
        cls.empty_raw = base64.b64decode(cls.empty_data["value_base64"], validate=True)

    def test_fixture_metadata_is_pinned_and_explained(self) -> None:
        self.assertEqual(self.null_data["id"], FIXTURE_ID)
        self.assertEqual(self.null_data["protocol"], 28)
        self.assertEqual(self.null_data["surface"], "xdr")
        self.assertEqual(self.null_data["type"], "ScVal")
        self.assertEqual(self.null_data["kind"], "roundtrip")
        self.assertIn(
            "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/",
            self.null_data["source_reference"],
        )
        self.assertIn("stellar-xdr 28.0.1", self.null_text)
        self.assertIn("to_xdr_base64(Limits::none())", self.null_text)
        self.assertIn("generated 2026-11-20 (UTC)", self.null_text)

    def test_null_and_empty_maps_are_distinct_encodings(self) -> None:
        self.assertNotEqual(self.null_raw, self.empty_raw)
        self.assertEqual(self.null_raw.hex(), "0000001100000000")
        self.assertEqual(self.empty_raw.hex(), "000000110000000100000000")

    def test_null_map_decodes_to_absent_and_empty_map_to_present_empty(self) -> None:
        self.assertEqual(scval_xdr.decode(self.null_raw), ("map", None))
        self.assertEqual(scval_xdr.decode(self.empty_raw), ("map", []))
        self.assertEqual(scval_xdr.encode(("map", None)), self.null_raw)
        self.assertEqual(scval_xdr.encode(("map", [])), self.empty_raw)

    def test_null_fixture_round_trips_byte_for_byte(self) -> None:
        self.assertEqual(scval_xdr.encode(scval_xdr.decode(self.null_raw)), self.null_raw)
        self.assertEqual(
            scval_xdr.to_json(scval_xdr.decode(self.null_raw)),
            {"type": "map", "value": None},
        )

    def test_evidence_record_binds_the_fixture_bytes(self) -> None:
        record_path = PACK / "evidence" / "records" / f"{FIXTURE_ID}.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["outcome"], "matched")
        self.assertEqual(
            record["fixtureSha256"],
            hashlib.sha256(NULL_PATH.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
