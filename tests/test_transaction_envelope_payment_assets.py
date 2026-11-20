"""Offline checks for the Protocol 28 issued-asset Payment fixtures.

The fixtures are synthetic structural data. They assert the AlphaNum4 and
AlphaNum12 asset codes and issuer fields inside a Payment; they do not claim
either asset is issued, funded or present on a network, and neither envelope
is a submitted transaction.
"""
from __future__ import annotations

import base64
import hashlib
import json
import tomllib
import unittest
from pathlib import Path

from tests import xdr_codec

REPO_ROOT = Path(__file__).resolve().parents[1]
ENVELOPE_DIR = REPO_ROOT / "protocol-28" / "xdr" / "transaction-envelope"
RECORDS_DIR = REPO_ROOT / "protocol-28" / "evidence" / "records"

CASES = {
    "p28-xdr-transaction-envelope-payment-credit-alphanum4": {
        "asset_type": xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4,
        "code": b"USD1",
        "issuer_byte": 0x76,
        "destination_byte": 0x75,
        "amount": 4_005,
        "length": 240,
    },
    "p28-xdr-transaction-envelope-payment-credit-alphanum12": {
        "asset_type": xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM12,
        "code": b"ABCDEFGHIJKL",
        "issuer_byte": 0x7A,
        "destination_byte": 0x79,
        "amount": 4_006,
        "length": 248,
    },
}


def load_fixture(fixture_id: str) -> dict:
    path = ENVELOPE_DIR / f"{fixture_id}.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_record(fixture_id: str) -> dict:
    path = RECORDS_DIR / f"{fixture_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class IssuedAssetPaymentEnvelopeTests(unittest.TestCase):
    def test_issued_asset_payments_roundtrip_with_code_and_issuer(self) -> None:
        for fixture_id, expected in CASES.items():
            with self.subTest(fixture=fixture_id):
                fixture = load_fixture(fixture_id)
                self.assertEqual(fixture["id"], fixture_id)
                self.assertEqual(fixture["protocol"], 28)
                self.assertEqual(fixture["surface"], "xdr")
                self.assertEqual(fixture["category"], "transaction-envelope")
                self.assertEqual(fixture["type"], "TransactionEnvelope")
                self.assertEqual(fixture["kind"], "roundtrip")
                self.assertIn(
                    "9c9c145953e80990d6ff1ae3a6a973a0ce6d0694",
                    fixture["source_reference"],
                )

                raw = base64.b64decode(fixture["value_base64"], validate=True)
                self.assertEqual(len(raw), expected["length"])
                envelope = xdr_codec.decode_transaction_envelope(raw)
                operation = envelope.v1.tx.operations[0]
                self.assertEqual(
                    operation.body.op_type, xdr_codec.OPERATION_TYPE_PAYMENT
                )
                payment = operation.body.payment
                self.assertEqual(
                    payment.destination,
                    xdr_codec.MuxedAccount(
                        key_type=xdr_codec.KEY_TYPE_ED25519,
                        ed25519=bytes([expected["destination_byte"]]) * 32,
                    ),
                )
                self.assertEqual(payment.asset.asset_type, expected["asset_type"])
                self.assertEqual(payment.amount, expected["amount"])

                if expected["asset_type"] == xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM4:
                    alpha = payment.asset.alpha_num4
                    self.assertIsNotNone(alpha)
                    self.assertEqual(alpha.asset_code, expected["code"])
                    issuer = alpha.issuer
                else:
                    alpha = payment.asset.alpha_num12
                    self.assertIsNotNone(alpha)
                    self.assertEqual(alpha.asset_code, expected["code"])
                    issuer = alpha.issuer

                self.assertEqual(issuer.key_type, xdr_codec.PUBLIC_KEY_TYPE_ED25519)
                self.assertEqual(
                    issuer.ed25519, bytes([expected["issuer_byte"]]) * 32
                )
                self.assertIn(expected["code"], raw)
                self.assertEqual(xdr_codec.encode_transaction_envelope(envelope), raw)

    def test_every_fixture_has_a_matching_structural_record(self) -> None:
        for fixture_id in CASES:
            with self.subTest(fixture=fixture_id):
                record = load_record(fixture_id)
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["outcome"], "matched")
                fixture_path = ENVELOPE_DIR / f"{fixture_id}.toml"
                self.assertEqual(
                    record["fixtureSha256"],
                    hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
