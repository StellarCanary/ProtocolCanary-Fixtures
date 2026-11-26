"""Focused offline checks for absent TransactionV0 time bounds (issue #535)."""
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

CAMPAIGN = REPO_ROOT / "protocol-28" / "xdr" / "campaign"
TRANSACTION_ENVELOPE = REPO_ROOT / "protocol-28" / "xdr" / "transaction-envelope"
RECORDS = REPO_ROOT / "protocol-28" / "evidence" / "records"
BASELINE_ID = "p28-xdr-transaction-envelope-v0-roundtrip"
FIXTURE_ID = "p28-xdr-transaction-v0-null-timebounds-absent"


def load_fixture() -> tuple[dict, bytes, Path]:
    path = CAMPAIGN / f"{FIXTURE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


def load_baseline() -> tuple[dict, bytes, Path]:
    path = TRANSACTION_ENVELOPE / f"{BASELINE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


class TransactionV0NullTimeBoundsTests(unittest.TestCase):
    def test_fixture_metadata_is_pinned(self) -> None:
        data, _, path = load_fixture()
        self.assertEqual(data["id"], FIXTURE_ID)
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["type"], "TransactionEnvelope")
        self.assertEqual(data["kind"], "roundtrip")
        self.assertIn("/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/", data["source_reference"])
        header = path.read_text(encoding="utf-8")
        self.assertIn("`stellar-xdr` 28.0.1", header)
        self.assertIn("time_bounds: None", header)

    def test_time_bounds_absent_pointer_and_unchanged_fields(self) -> None:
        _, raw, _ = load_fixture()
        decoded = xdr_codec.decode_transaction_envelope(raw)
        generic = xdr_codec.decode_xdr("TransactionEnvelope", raw)
        self.assertEqual(decoded, generic)
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX_V0)
        self.assertIsNone(decoded.v0.tx.time_bounds)
        self.assertEqual(decoded.v0.tx.source_account_ed25519, b"\x11" * 32)
        self.assertEqual(decoded.v0.tx.fee, 100)
        self.assertEqual(decoded.v0.tx.seq_num, 1_234_567)
        self.assertEqual(decoded.v0.tx.memo.memo_type, xdr_codec.MEMO_NONE)
        self.assertEqual(decoded.v0.tx.ext_type, 0)
        self.assertEqual(len(decoded.v0.tx.operations), 1)

        _, baseline_raw, _ = load_baseline()
        baseline = xdr_codec.decode_transaction_envelope(baseline_raw)
        self.assertIsNotNone(baseline.v0.tx.time_bounds)
        self.assertEqual(decoded.v0.tx.operations, baseline.v0.tx.operations)
        self.assertEqual(decoded.v0.signatures, baseline.v0.signatures)
        self.assertEqual(decoded.v0.tx.memo, baseline.v0.tx.memo)
        self.assertEqual(decoded.v0.tx.ext_type, baseline.v0.tx.ext_type)
        self.assertEqual(len(baseline_raw) - len(raw), 16)
        self.assertEqual(baseline_raw[48:52], (1).to_bytes(4, "big"))
        self.assertEqual(raw[48:52], (0).to_bytes(4, "big"))

    def test_exact_roundtrip_with_both_codec_interfaces(self) -> None:
        _, raw, _ = load_fixture()
        decoded = xdr_codec.decode_transaction_envelope(raw)
        self.assertEqual(xdr_codec.encode_transaction_envelope(decoded), raw)
        self.assertEqual(xdr_codec.encode_xdr("TransactionEnvelope", decoded), raw)

    def test_structural_record_binds_the_fixture_bytes(self) -> None:
        _, _, path = load_fixture()
        record = json.loads((RECORDS / f"{FIXTURE_ID}.json").read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["fixtureSha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
