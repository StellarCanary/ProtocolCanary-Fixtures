"""Focused test for Transaction operation vector length limits (issue #532)."""
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

CAMPAIGN_DIR = REPO_ROOT / "protocol-28" / "xdr" / "campaign"
RECORDS_DIR = REPO_ROOT / "protocol-28" / "evidence" / "records"
BASELINE_PATH = (
    REPO_ROOT
    / "protocol-28"
    / "xdr"
    / "transaction-envelope"
    / "p28-xdr-transaction-envelope-v1-roundtrip.toml"
)

EMPTY_ID = "p28-xdr-transaction-operation-count-empty"
MAXIMUM_ID = "p28-xdr-transaction-operation-count-maximum"
OVER_LIMIT_ID = "p28-xdr-transaction-operation-count-over-limit"


def load_fixture(path: Path) -> tuple[dict, bytes]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True)


class TransactionOperationCountTests(unittest.TestCase):
    def test_empty_operations_vector_decodes_and_roundtrips(self) -> None:
        fixture_path = CAMPAIGN_DIR / f"{EMPTY_ID}.toml"
        data, raw = load_fixture(fixture_path)

        self.assertEqual(data["id"], EMPTY_ID)
        self.assertEqual(data["type"], "TransactionEnvelope")
        self.assertEqual(data["kind"], "roundtrip")
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "transaction-envelope")

        # Decode with both decoders
        decoded = xdr_codec.decode_transaction_envelope(raw)
        decoded_generic = xdr_codec.decode_xdr("TransactionEnvelope", raw)
        self.assertEqual(decoded, decoded_generic)
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)

        tx = decoded.v1.tx
        # Assert Transaction.operations is length 0 elements
        self.assertEqual(len(tx.operations), 0)
        self.assertEqual(tx.operations, [])

        # Exact byte-for-byte roundtrip with both encoders
        self.assertEqual(raw, xdr_codec.encode_transaction_envelope(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("TransactionEnvelope", decoded))

        # Size check: 144 bytes (baseline 200 bytes minus 56-byte Payment operation)
        self.assertEqual(len(raw), 144)
        _, base_raw = load_fixture(BASELINE_PATH)
        self.assertEqual(len(base_raw) - len(raw), 56)

    def test_maximum_operations_vector_decodes_and_roundtrips(self) -> None:
        fixture_path = CAMPAIGN_DIR / f"{MAXIMUM_ID}.toml"
        data, raw = load_fixture(fixture_path)

        self.assertEqual(data["id"], MAXIMUM_ID)
        self.assertEqual(data["type"], "TransactionEnvelope")
        self.assertEqual(data["kind"], "roundtrip")
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "transaction-envelope")

        # Decode with both decoders
        decoded = xdr_codec.decode_transaction_envelope(raw)
        decoded_generic = xdr_codec.decode_xdr("TransactionEnvelope", raw)
        self.assertEqual(decoded, decoded_generic)
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)

        tx = decoded.v1.tx
        # Assert Transaction.operations is length 100 elements
        self.assertEqual(len(tx.operations), 100)

        # Baseline payment operation comparison
        _, base_raw = load_fixture(BASELINE_PATH)
        base = xdr_codec.decode_transaction_envelope(base_raw)
        base_payment_op = base.v1.tx.operations[0]

        for op in tx.operations:
            self.assertEqual(op.source_account, base_payment_op.source_account)
            self.assertEqual(op.body.op_type, xdr_codec.OPERATION_TYPE_PAYMENT)
            self.assertEqual(op.body.payment.destination, base_payment_op.body.payment.destination)
            self.assertEqual(op.body.payment.asset, base_payment_op.body.payment.asset)
            self.assertEqual(op.body.payment.amount, base_payment_op.body.payment.amount)

        # Confirm byte offset 60..64 holds length 100
        count_at_60 = int.from_bytes(raw[60:64], "big")
        self.assertEqual(count_at_60, 100)

        # Exact byte-for-byte roundtrip with both encoders
        self.assertEqual(raw, xdr_codec.encode_transaction_envelope(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("TransactionEnvelope", decoded))

        # Size check: 5,744 bytes (144 base envelope bytes + 100 * 56 bytes)
        self.assertEqual(len(raw), 5744)

    def test_over_limit_operations_vector_rejected_by_both_decoders(self) -> None:
        max_fixture_path = CAMPAIGN_DIR / f"{MAXIMUM_ID}.toml"
        _, max_raw = load_fixture(max_fixture_path)

        over_fixture_path = CAMPAIGN_DIR / f"{OVER_LIMIT_ID}.toml"
        data, over_raw = load_fixture(over_fixture_path)

        self.assertEqual(data["id"], OVER_LIMIT_ID)
        self.assertEqual(data["type"], "TransactionEnvelope")
        self.assertEqual(data["kind"], "decode-failure")
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "transaction-envelope")

        # Verify mutation: exactly byte offset 60..64 replaced with 101
        self.assertEqual(len(over_raw), len(max_raw))
        self.assertEqual(over_raw[:60], max_raw[:60])
        self.assertEqual(over_raw[64:], max_raw[64:])
        self.assertEqual(over_raw[60:64], (101).to_bytes(4, "big"))

        # Verify rejection with both decoders and assert error identifies limit
        with self.assertRaises(xdr_codec.XdrCodecError) as ctx1:
            xdr_codec.decode_transaction_envelope(over_raw)
        self.assertIn("operations length prefix 101 exceeds maximum 100", str(ctx1.exception))

        with self.assertRaises(xdr_codec.XdrCodecError) as ctx2:
            xdr_codec.decode_xdr("TransactionEnvelope", over_raw)
        self.assertIn("operations length prefix 101 exceeds maximum 100", str(ctx2.exception))

    def test_structural_records_exist_and_bind_fixtures(self) -> None:
        for fixture_id in (EMPTY_ID, MAXIMUM_ID, OVER_LIMIT_ID):
            with self.subTest(fixture_id=fixture_id):
                record_path = RECORDS_DIR / f"{fixture_id}.json"
                fixture_path = CAMPAIGN_DIR / f"{fixture_id}.toml"

                self.assertTrue(record_path.is_file(), f"Missing record: {record_path}")
                record = json.loads(record_path.read_text(encoding="utf-8"))

                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["outcome"], "matched")
                self.assertEqual(
                    record["fixtureSha256"],
                    hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
