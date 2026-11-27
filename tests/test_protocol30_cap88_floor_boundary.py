"""Focused offline checks for CAP-88 floor rounding at a 999 ms remainder (issue #517)."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import xdr_codec  # noqa: E402

PACK = REPO_ROOT / "protocol-30"
FIXTURES = PACK / "xdr" / "cap-0088"
RECORDS = PACK / "evidence" / "records"
SIGNED_ID = "p30-xdr-cap0088-stellar-value-signed-ms-999ms"
EMPTY_ID = "p30-xdr-cap0088-stellar-value-empty-tx-set-ms-999ms"
CLOSE_TIME = 1_700_000_123
CLOSE_TIME_MS = 1_700_000_123_999


def load(fixture_id: str) -> tuple[dict, str, bytes]:
    path = FIXTURES / f"{fixture_id}.toml"
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


class Cap88FloorBoundaryTests(unittest.TestCase):
    def test_fixture_metadata_and_provenance(self) -> None:
        for fixture_id in (SIGNED_ID, EMPTY_ID):
            with self.subTest(fixture_id=fixture_id):
                data, text, _ = load(fixture_id)
                self.assertEqual(data["id"], fixture_id)
                self.assertEqual(data["protocol"], 30)
                self.assertEqual(data["surface"], "xdr")
                self.assertEqual(data["category"], "cap-0088")
                self.assertEqual(data["type"], "StellarValue")
                self.assertEqual(data["kind"], "roundtrip")
                self.assertIn("1ae39233055a0fb94bb737650a39ede8d77d924c", data["source_reference"])
                self.assertIn("stellar-xdr 30.0.0", text)
                self.assertIn("1_700_000_123_999", text)
                self.assertIn("floor", text.lower())

    def test_signed_ms_floor_boundary(self) -> None:
        _, _, raw = load(SIGNED_ID)
        value = xdr_codec.decode_stellar_value(raw)
        self.assertEqual(value, xdr_codec.decode_xdr("StellarValue", raw))
        self.assertEqual(value.tx_set_hash, bytes([0x11]) * 32)
        self.assertEqual(value.close_time, CLOSE_TIME)
        self.assertEqual(value.upgrades, [])
        self.assertEqual(value.ext.ext_type, xdr_codec.STELLAR_VALUE_SIGNED_MS)

        signed_ms = value.ext.signed_ms_value
        self.assertIsNotNone(signed_ms)
        self.assertEqual(signed_ms.close_time_ms, CLOSE_TIME_MS)
        self.assertEqual(signed_ms.close_time_ms % 1000, 999)
        self.assertEqual(value.close_time, signed_ms.close_time_ms // 1000)
        self.assertNotEqual(value.close_time, (signed_ms.close_time_ms + 500) // 1000)
        self.assertEqual(signed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32)
        self.assertEqual(signed_ms.lc_value_signature.signature, bytes([0x55]) * 64)

        self.assertEqual(raw, xdr_codec.encode_stellar_value(value))
        self.assertEqual(raw, xdr_codec.encode_xdr("StellarValue", value))

    def test_empty_tx_set_ms_floor_boundary(self) -> None:
        _, _, raw = load(EMPTY_ID)
        value = xdr_codec.decode_stellar_value(raw)
        self.assertEqual(value, xdr_codec.decode_xdr("StellarValue", raw))
        self.assertEqual(value.tx_set_hash, bytes(32))
        self.assertEqual(value.close_time, CLOSE_TIME)
        self.assertEqual(value.upgrades, [])
        self.assertEqual(value.ext.ext_type, xdr_codec.STELLAR_VALUE_EMPTY_TX_SET_MS)

        proposed_ms = value.ext.proposed_ms_value
        self.assertIsNotNone(proposed_ms)
        self.assertEqual(proposed_ms.close_time_ms, CLOSE_TIME_MS)
        self.assertEqual(proposed_ms.close_time_ms % 1000, 999)
        self.assertEqual(value.close_time, proposed_ms.close_time_ms // 1000)
        self.assertNotEqual(value.close_time, (proposed_ms.close_time_ms + 500) // 1000)
        self.assertEqual(proposed_ms.tx_set_hash, bytes([0x33]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_hash, bytes([0x44]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_version, 30)
        self.assertEqual(proposed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32)
        self.assertEqual(proposed_ms.lc_value_signature.signature, bytes([0x55]) * 64)

        self.assertEqual(raw, xdr_codec.encode_stellar_value(value))
        self.assertEqual(raw, xdr_codec.encode_xdr("StellarValue", value))

    def test_evidence_records_bind_the_fixture_bytes(self) -> None:
        for fixture_id in (SIGNED_ID, EMPTY_ID):
            with self.subTest(fixture_id=fixture_id):
                record = json.loads((RECORDS / f"{fixture_id}.json").read_text(encoding="utf-8"))
                fixture_path = FIXTURES / f"{fixture_id}.toml"
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["outcome"], "matched")
                self.assertEqual(
                    record["fixtureSha256"], hashlib.sha256(fixture_path.read_bytes()).hexdigest()
                )


if __name__ == "__main__":
    unittest.main()
