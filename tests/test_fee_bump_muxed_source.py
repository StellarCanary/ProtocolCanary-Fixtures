"""Focused offline checks for a muxed fee-bump fee source (issue #536)."""
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
BASELINE_ID = "p28-xdr-transaction-envelope-fee-bump-roundtrip"
FIXTURE_ID = "p28-xdr-fee-bump-muxed-source-muxed"
KEY_TYPE_MUXED_ED25519 = 0x100


def load_fixture() -> tuple[dict, bytes, Path]:
    path = CAMPAIGN / f"{FIXTURE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


def load_baseline() -> tuple[dict, bytes, Path]:
    path = TRANSACTION_ENVELOPE / f"{BASELINE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


class FeeBumpMuxedSourceTests(unittest.TestCase):
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
        self.assertIn("MuxedAccountMed25519", header)

    def test_fee_source_is_the_muxed_composite_layout(self) -> None:
        _, raw, _ = load_fixture()
        decoded = xdr_codec.decode_transaction_envelope(raw)
        generic = xdr_codec.decode_xdr("TransactionEnvelope", raw)
        self.assertEqual(decoded, generic)
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX_FEE_BUMP)
        fee_source = decoded.fee_bump.tx.fee_source
        self.assertEqual(fee_source.key_type, KEY_TYPE_MUXED_ED25519)
        self.assertIsNone(fee_source.ed25519)
        self.assertIsNotNone(fee_source.muxed)
        self.assertEqual(fee_source.muxed.id, 7)
        self.assertEqual(fee_source.muxed.ed25519, b"\xcc" * 32)
        self.assertEqual(raw[4:8], KEY_TYPE_MUXED_ED25519.to_bytes(4, "big"))
        self.assertEqual(raw[8:16], (7).to_bytes(8, "big"))
        self.assertEqual(raw[16:48], b"\xcc" * 32)

    def test_inner_envelope_and_outer_fields_are_preserved(self) -> None:
        _, raw, _ = load_fixture()
        _, baseline_raw, _ = load_baseline()
        decoded = xdr_codec.decode_transaction_envelope(raw)
        baseline = xdr_codec.decode_transaction_envelope(baseline_raw)
        self.assertEqual(decoded.fee_bump.tx.fee, baseline.fee_bump.tx.fee)
        self.assertEqual(decoded.fee_bump.tx.inner_tx, baseline.fee_bump.tx.inner_tx)
        self.assertEqual(decoded.fee_bump.tx.ext_type, baseline.fee_bump.tx.ext_type)
        self.assertEqual(decoded.fee_bump.signatures, baseline.fee_bump.signatures)
        self.assertEqual(baseline.fee_bump.tx.fee_source.key_type, xdr_codec.KEY_TYPE_ED25519)
        self.assertEqual(len(raw) - len(baseline_raw), 8)

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
