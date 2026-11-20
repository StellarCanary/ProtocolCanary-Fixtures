"""Offline checks for the Protocol 28 Memo-arm envelope fixtures.

Each fixture is synthetic structural data. The valid fixtures must decode
and re-encode byte-for-byte; the too-long text memo must be rejected at the
declared 28-byte limit. None of these values is a submitted transaction.
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

ROUNDTRIP_CASES = {
    "p28-xdr-transaction-envelope-memo-text-max": xdr_codec.Memo(
        memo_type=xdr_codec.MEMO_TEXT,
        text="ABCDEFGHIJKLMNOPQRSTUVWXYZ12",
    ),
    "p28-xdr-transaction-envelope-memo-id-max": xdr_codec.Memo(
        memo_type=xdr_codec.MEMO_ID,
        id=(1 << 64) - 1,
    ),
    "p28-xdr-transaction-envelope-memo-hash": xdr_codec.Memo(
        memo_type=xdr_codec.MEMO_HASH,
        hash=b"\x68" * 32,
    ),
    "p28-xdr-transaction-envelope-memo-return": xdr_codec.Memo(
        memo_type=xdr_codec.MEMO_RETURN,
        hash=b"\x6c" * 32,
    ),
}
TOO_LONG_ID = "p28-xdr-transaction-envelope-memo-text-too-long"


def load_fixture(fixture_id: str) -> dict:
    path = ENVELOPE_DIR / f"{fixture_id}.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_record(fixture_id: str) -> dict:
    path = RECORDS_DIR / f"{fixture_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class MemoVariantEnvelopeTests(unittest.TestCase):
    def test_roundtrip_memo_arms_preserve_their_values_and_bytes(self) -> None:
        for fixture_id, expected_memo in ROUNDTRIP_CASES.items():
            with self.subTest(fixture=fixture_id):
                fixture = load_fixture(fixture_id)
                self.assertEqual(fixture["id"], fixture_id)
                self.assertEqual(fixture["protocol"], 28)
                self.assertEqual(fixture["surface"], "xdr")
                self.assertEqual(fixture["type"], "TransactionEnvelope")
                self.assertEqual(fixture["kind"], "roundtrip")
                self.assertIn(
                    "9c9c145953e80990d6ff1ae3a6a973a0ce6d0694",
                    fixture["source_reference"],
                )

                raw = base64.b64decode(fixture["value_base64"], validate=True)
                envelope = xdr_codec.decode_transaction_envelope(raw)
                self.assertEqual(envelope.v1.tx.memo, expected_memo)
                self.assertEqual(xdr_codec.encode_transaction_envelope(envelope), raw)

    def test_maximum_text_memo_is_exactly_28_bytes(self) -> None:
        fixture = load_fixture("p28-xdr-transaction-envelope-memo-text-max")
        raw = base64.b64decode(fixture["value_base64"], validate=True)
        envelope = xdr_codec.decode_transaction_envelope(raw)
        text = envelope.v1.tx.memo.text
        self.assertIsNotNone(text)
        self.assertEqual(len(text.encode("ascii")), xdr_codec.MAX_MEMO_TEXT)
        self.assertEqual(xdr_codec.MAX_MEMO_TEXT, 28)

    def test_maximum_id_uses_all_eight_bytes(self) -> None:
        fixture = load_fixture("p28-xdr-transaction-envelope-memo-id-max")
        raw = base64.b64decode(fixture["value_base64"], validate=True)
        envelope = xdr_codec.decode_transaction_envelope(raw)
        self.assertEqual(envelope.v1.tx.memo.id, (1 << 64) - 1)
        self.assertIn(b"\xff" * 8, raw)

    def test_too_long_text_memo_is_rejected_at_the_declared_limit(self) -> None:
        fixture = load_fixture(TOO_LONG_ID)
        self.assertEqual(fixture["kind"], "decode-failure")
        raw = base64.b64decode(fixture["value_base64"], validate=True)
        self.assertEqual(len(raw), 236)
        with self.assertRaisesRegex(
            xdr_codec.XdrCodecError,
            "length prefix 29 exceeds maximum allowed 28",
        ):
            xdr_codec.decode_transaction_envelope(raw)

    def test_too_long_fixture_is_the_documented_mutation_of_the_max_fixture(self) -> None:
        max_fixture = load_fixture("p28-xdr-transaction-envelope-memo-text-max")
        too_long = load_fixture(TOO_LONG_ID)
        valid = base64.b64decode(max_fixture["value_base64"], validate=True)
        invalid = base64.b64decode(too_long["value_base64"], validate=True)

        # Envelope type (4) + source account (4 + 32) + fee (4) + sequence
        # number (8) + preconditions (4) + memo type (4) = 60.
        memo_length_offset = 60
        self.assertEqual(valid[memo_length_offset : memo_length_offset + 4], (28).to_bytes(4, "big"))
        self.assertEqual(invalid[memo_length_offset : memo_length_offset + 4], (29).to_bytes(4, "big"))

        text_offset = memo_length_offset + 4
        self.assertEqual(valid[text_offset : text_offset + 28], b"ABCDEFGHIJKLMNOPQRSTUVWXYZ12")
        self.assertEqual(
            invalid[text_offset : text_offset + 32],
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZ12X\x00\x00\x00",
        )
        self.assertEqual(invalid[text_offset + 32 :], valid[text_offset + 28 :])

    def test_every_fixture_has_a_matching_structural_record(self) -> None:
        for fixture_id in [*ROUNDTRIP_CASES, TOO_LONG_ID]:
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
