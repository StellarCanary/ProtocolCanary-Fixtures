"""Focused offline checks for TransactionV1Envelope signature vector bounds (issue #533)."""
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
BASELINE_ID = "p28-xdr-transaction-envelope-v1-roundtrip"
EMPTY_ID = "p28-xdr-transaction-signature-count-empty"
MAXIMUM_ID = "p28-xdr-transaction-signature-count-maximum"
OVER_LIMIT_ID = "p28-xdr-transaction-signature-count-over-limit"
FIXTURE_IDS = (EMPTY_ID, MAXIMUM_ID, OVER_LIMIT_ID)


def load(fixture_id: str) -> tuple[dict, bytes, Path]:
    path = CAMPAIGN / f"{fixture_id}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


def decode_both(raw: bytes) -> tuple[xdr_codec.TransactionEnvelope, xdr_codec.TransactionEnvelope]:
    return xdr_codec.decode_transaction_envelope(raw), xdr_codec.decode_xdr("TransactionEnvelope", raw)


def load_baseline() -> tuple[dict, bytes, Path]:
    path = TRANSACTION_ENVELOPE / f"{BASELINE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


class TransactionSignatureCountTests(unittest.TestCase):
    def test_fixture_metadata_is_pinned(self) -> None:
        for fixture_id in FIXTURE_IDS:
            with self.subTest(fixture_id=fixture_id):
                data, _, _ = load(fixture_id)
                self.assertEqual(data["id"], fixture_id)
                self.assertEqual(data["protocol"], 28)
                self.assertEqual(data["surface"], "xdr")
                self.assertEqual(data["type"], "TransactionEnvelope")
                self.assertIn(
                    "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/",
                    data["source_reference"],
                )

    def test_empty_vector_and_unchanged_transaction_fields(self) -> None:
        data, raw, path = load(EMPTY_ID)
        self.assertEqual(data["kind"], "roundtrip")
        decoded, generic = decode_both(raw)
        self.assertEqual(decoded, generic)
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
        self.assertEqual(decoded.v1.signatures, [])
        self.assertEqual(len(raw), 128)

        _, baseline_raw, _ = load_baseline()
        baseline = xdr_codec.decode_transaction_envelope(baseline_raw)
        self.assertEqual(decoded.v1.tx, baseline.v1.tx)
        self.assertEqual(baseline_raw[124:128], (1).to_bytes(4, "big"))
        self.assertEqual(raw[124:128], (0).to_bytes(4, "big"))

        self.assertEqual(xdr_codec.encode_transaction_envelope(decoded), raw)
        self.assertEqual(xdr_codec.encode_xdr("TransactionEnvelope", decoded), raw)
        self.assertIn("`stellar-xdr` 28.0.1", path.read_text(encoding="utf-8"))

    def test_maximum_vector_and_exact_signature_bytes(self) -> None:
        data, raw, path = load(MAXIMUM_ID)
        self.assertEqual(data["kind"], "roundtrip")
        decoded, generic = decode_both(raw)
        self.assertEqual(decoded, generic)
        self.assertEqual(decoded.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
        self.assertEqual(len(decoded.v1.signatures), 20)
        self.assertEqual(raw[124:128], (20).to_bytes(4, "big"))
        self.assertEqual(len(raw), 1568)

        expected = xdr_codec.DecoratedSignature(
            hint=b"\x66" * 4,
            signature=b"\x66" * 64,
        )
        for signature in decoded.v1.signatures:
            self.assertEqual(signature, expected)

        _, baseline_raw, _ = load_baseline()
        baseline = xdr_codec.decode_transaction_envelope(baseline_raw)
        self.assertEqual(decoded.v1.tx, baseline.v1.tx)
        self.assertEqual(decoded.v1.signatures[0], baseline.v1.signatures[0])
        self.assertEqual(baseline_raw[124:128], (1).to_bytes(4, "big"))

        self.assertEqual(xdr_codec.encode_transaction_envelope(decoded), raw)
        self.assertEqual(xdr_codec.encode_xdr("TransactionEnvelope", decoded), raw)
        self.assertIn("`stellar-xdr` 28.0.1", path.read_text(encoding="utf-8"))

    def test_over_limit_is_one_count_word_mutation_of_maximum(self) -> None:
        data, raw, path = load(OVER_LIMIT_ID)
        self.assertEqual(data["kind"], "decode-failure")
        _, maximum_raw, _ = load(MAXIMUM_ID)
        self.assertEqual(maximum_raw[124:128], (20).to_bytes(4, "big"))
        expected = maximum_raw[:124] + (21).to_bytes(4, "big") + maximum_raw[128:]
        self.assertEqual(raw, expected)
        self.assertIn("over[124..128]", path.read_text(encoding="utf-8"))

    def test_over_limit_is_rejected_by_both_decoders_with_limit_error(self) -> None:
        _, raw, _ = load(OVER_LIMIT_ID)
        decoders = (
            ("decode_transaction_envelope", xdr_codec.decode_transaction_envelope),
            ("decode_xdr", lambda value: xdr_codec.decode_xdr("TransactionEnvelope", value)),
        )
        for name, decoder in decoders:
            with self.subTest(decoder=name):
                with self.assertRaises(xdr_codec.XdrCodecError) as caught:
                    decoder(raw)
                message = str(caught.exception)
                self.assertIn("signatures length prefix 21 exceeds maximum 20", message)

    def test_each_fixture_has_a_bound_structural_record(self) -> None:
        for fixture_id in FIXTURE_IDS:
            with self.subTest(fixture_id=fixture_id):
                _, _, path = load(fixture_id)
                record = json.loads((RECORDS / f"{fixture_id}.json").read_text(encoding="utf-8"))
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["fixtureSha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
