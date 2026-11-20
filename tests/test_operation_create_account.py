"""Focused tests for Protocol 28 TransactionEnvelope embedding CREATE_ACCOUNT (issue #540).

Asserts:
- Decoded OperationBody::CREATE_ACCOUNT arm (OperationType 0).
- Decoded destination AccountID (PublicKeyTypeEd25519 sentinel).
- Decoded signed startingBalance boundary value (i64::MAX = 9223372036854775807).
- Exact byte-for-byte roundtrip through independent Python TransactionEnvelope codec.
- Structural rejections (truncation, trailing bytes, invalid discriminant)
  are rejected by the independent codec.
"""
from __future__ import annotations

import base64
import sys
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import operation_xdr, xdr_codec

FIXTURE_PATH = (
    REPO_ROOT
    / "protocol-28"
    / "xdr"
    / "campaign"
    / "p28-xdr-operation-create_account.toml"
)

INT64_MAX = (1 << 63) - 1


def load_fixture(path: Path) -> tuple[dict, bytes]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True)


class OperationCreateAccountTests(unittest.TestCase):
    def test_fixture_metadata_and_decoded_fields(self) -> None:
        data, raw = load_fixture(FIXTURE_PATH)
        self.assertEqual(data["id"], "p28-xdr-operation-create_account")
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "transaction-envelope")
        self.assertEqual(data["type"], "TransactionEnvelope")
        self.assertEqual(data["kind"], "roundtrip")

        # Decode through the independent Python TransactionEnvelope codec
        envelope = xdr_codec.decode_transaction_envelope(raw)
        envelope_generic = xdr_codec.decode_xdr("TransactionEnvelope", raw)
        self.assertEqual(envelope, envelope_generic)

        # Envelope assertions
        self.assertEqual(envelope.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
        self.assertIsNotNone(envelope.v1)
        v1 = envelope.v1
        self.assertIsNotNone(v1)
        self.assertEqual(len(v1.tx.operations), 1)

        # Operation assertions
        op = v1.tx.operations[0]
        self.assertIsNone(op.source_account)
        self.assertEqual(
            op.body.op_type, operation_xdr.OPERATION_TYPE_CREATE_ACCOUNT
        )
        self.assertEqual(op.body.op_type, 0)

        # CreateAccountOp payload assertions
        create_op = op.body.operation
        self.assertIsInstance(create_op, operation_xdr.CreateAccountOp)

        # Destination AccountID assertions
        dest = create_op.destination
        self.assertIsInstance(dest, xdr_codec.PublicKey)
        self.assertEqual(dest.key_type, xdr_codec.PUBLIC_KEY_TYPE_ED25519)
        self.assertEqual(dest.key_type, 0)
        self.assertEqual(dest.ed25519, bytes([0x55]) * 32)

        # Signed startingBalance boundary value assertion
        self.assertEqual(create_op.starting_balance, INT64_MAX)
        self.assertEqual(create_op.starting_balance, 9_223_372_036_854_775_807)

        # Exact byte-for-byte re-encoding
        re_encoded = xdr_codec.encode_transaction_envelope(envelope)
        self.assertEqual(raw, re_encoded)
        self.assertEqual(raw, xdr_codec.encode_xdr("TransactionEnvelope", envelope))

    def test_rejected_malformed_inputs(self) -> None:
        _, raw = load_fixture(FIXTURE_PATH)

        # Truncation at end
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_transaction_envelope(raw[:-1])

        # Truncation in operation body
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_transaction_envelope(raw[:80])

        # Trailing unconsumed bytes
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_transaction_envelope(raw + b"\x00")

        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_transaction_envelope(raw + b"\x00\x00\x00\x01")

        # Invalid envelope type discriminant (first 4 bytes)
        mutated_env = bytearray(raw)
        mutated_env[0:4] = (99).to_bytes(4, "big")
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_transaction_envelope(bytes(mutated_env))

    def test_encoder_rejects_out_of_range_balance(self) -> None:
        _, raw = load_fixture(FIXTURE_PATH)
        envelope = xdr_codec.decode_transaction_envelope(raw)
        assert envelope.v1 is not None
        op = envelope.v1.tx.operations[0]

        # Balance > int64 MAX
        invalid_op_overflow = replace(
            op,
            body=replace(
                op.body,
                operation=replace(
                    op.body.operation, starting_balance=(1 << 63)
                ),
            ),
        )
        invalid_tx_overflow = replace(
            envelope.v1.tx, operations=[invalid_op_overflow]
        )
        invalid_envelope_overflow = replace(
            envelope,
            v1=replace(envelope.v1, tx=invalid_tx_overflow),
        )
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.encode_transaction_envelope(invalid_envelope_overflow)

        # Balance < int64 MIN
        invalid_op_underflow = replace(
            op,
            body=replace(
                op.body,
                operation=replace(
                    op.body.operation, starting_balance=-(1 << 63) - 1
                ),
            ),
        )
        invalid_tx_underflow = replace(
            envelope.v1.tx, operations=[invalid_op_underflow]
        )
        invalid_envelope_underflow = replace(
            envelope,
            v1=replace(envelope.v1, tx=invalid_tx_underflow),
        )
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.encode_transaction_envelope(invalid_envelope_underflow)


if __name__ == "__main__":
    unittest.main()
