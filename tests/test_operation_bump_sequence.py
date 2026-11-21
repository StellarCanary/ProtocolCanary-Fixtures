"""Focused test for TransactionEnvelope with BUMP_SEQUENCE signed boundary (issue #545)."""
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

from tests import operation_xdr, xdr_codec  # noqa: E402

FIXTURE_ID = "p28-xdr-operation-bump_sequence"
FIXTURE = REPO_ROOT / "protocol-28" / "xdr" / "campaign" / f"{FIXTURE_ID}.toml"
BASELINE = (
    REPO_ROOT
    / "protocol-28"
    / "xdr"
    / "transaction-envelope"
    / "p28-xdr-transaction-envelope-v1-roundtrip.toml"
)
RECORD = REPO_ROOT / "protocol-28" / "evidence" / "records" / f"{FIXTURE_ID}.json"


def load(path: Path) -> tuple[dict, bytes]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True)


class OperationBumpSequenceTests(unittest.TestCase):
    def test_bump_sequence_envelope_decodes_and_roundtrips(self) -> None:
        data, raw = load(FIXTURE)
        self.assertEqual(data["id"], FIXTURE_ID)
        self.assertEqual(data["type"], "TransactionEnvelope")
        self.assertEqual(data["kind"], "roundtrip")
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "transaction-envelope")

        decoded = xdr_codec.decode_transaction_envelope(raw)
        self.assertEqual(decoded, xdr_codec.decode_xdr("TransactionEnvelope", raw))
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)

        tx = decoded.v1.tx
        self.assertEqual(len(tx.operations), 1)

        op = tx.operations[0]
        self.assertIsNone(op.source_account)
        self.assertEqual(op.body.op_type, operation_xdr.OPERATION_TYPE_BUMP_SEQUENCE)
        self.assertEqual(op.body.op_type, 11)

        payload = op.body.operation
        self.assertIsInstance(payload, operation_xdr.BumpSequenceOp)
        self.assertEqual(payload.bump_to, -(1 << 63))
        self.assertEqual(payload.bump_to, -9223372036854775808)

        # Independent Python codec re-encodes byte-for-byte
        self.assertEqual(raw, xdr_codec.encode_transaction_envelope(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("TransactionEnvelope", decoded))

    def test_only_operation_payload_differs_from_baseline(self) -> None:
        _, raw = load(FIXTURE)
        _, base_raw = load(BASELINE)
        base = xdr_codec.decode_transaction_envelope(base_raw)
        new = xdr_codec.decode_transaction_envelope(raw)

        # Common envelope header and transaction fields remain identical to baseline
        self.assertEqual(new.envelope_type, base.envelope_type)
        self.assertEqual(new.v1.signatures, base.v1.signatures)
        self.assertEqual(new.v1.tx.source_account, base.v1.tx.source_account)
        self.assertEqual(new.v1.tx.fee, base.v1.tx.fee)
        self.assertEqual(new.v1.tx.seq_num, base.v1.tx.seq_num)
        self.assertEqual(new.v1.tx.cond, base.v1.tx.cond)
        self.assertEqual(new.v1.tx.memo, base.v1.tx.memo)
        self.assertEqual(new.v1.tx.ext, base.v1.tx.ext)

        # Baseline has PaymentOp (56 bytes operation); BumpSequenceOp has 16 bytes.
        self.assertEqual(base.v1.tx.operations[0].body.op_type, 1)
        self.assertEqual(new.v1.tx.operations[0].body.op_type, 11)
        self.assertEqual(len(base_raw), 200)
        self.assertEqual(len(raw), 160)
        self.assertEqual(len(base_raw) - len(raw), 40)

    def test_structural_record_exists_and_binds_fixture(self) -> None:
        self.assertTrue(RECORD.is_file(), f"Missing structural record: {RECORD}")
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["outcome"], "matched")
        self.assertEqual(
            record["fixtureSha256"],
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
