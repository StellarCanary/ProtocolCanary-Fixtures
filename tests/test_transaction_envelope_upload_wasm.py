"""Offline checks for the Protocol 28 UPLOAD_CONTRACT_WASM envelope fixture.

The fixture is synthetic structural data, not a submitted transaction. It
asserts only that the Engine-independent codec preserves the opaque Wasm
payload and the surrounding envelope byte-for-byte.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import tomllib
import unittest
from pathlib import Path

from tests import xdr_codec

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPO_ROOT
    / "protocol-28"
    / "xdr"
    / "transaction-envelope"
    / "p28-xdr-transaction-envelope-upload-contract-wasm.toml"
)
RECORD = (
    REPO_ROOT
    / "protocol-28"
    / "evidence"
    / "records"
    / "p28-xdr-transaction-envelope-upload-contract-wasm.json"
)
MINIMAL_WASM = b"\x00asm\x01\x00\x00\x00"


def load_fixture() -> dict:
    with FIXTURE.open("rb") as handle:
        return tomllib.load(handle)


class UploadContractWasmEnvelopeTests(unittest.TestCase):
    def test_fixture_metadata_and_pinned_source(self) -> None:
        fixture = load_fixture()
        self.assertEqual(
            fixture["id"], "p28-xdr-transaction-envelope-upload-contract-wasm"
        )
        self.assertEqual(fixture["protocol"], 28)
        self.assertEqual(fixture["surface"], "xdr")
        self.assertEqual(fixture["category"], "transaction-envelope")
        self.assertEqual(fixture["type"], "TransactionEnvelope")
        self.assertEqual(fixture["kind"], "roundtrip")
        self.assertIn(
            "9c9c145953e80990d6ff1ae3a6a973a0ce6d0694",
            fixture["source_reference"],
        )

    def test_upload_wasm_envelope_roundtrips_and_preserves_wasm_bytes(self) -> None:
        fixture = load_fixture()
        raw = base64.b64decode(fixture["value_base64"], validate=True)
        self.assertEqual(len(raw), 204)

        envelope = xdr_codec.decode_transaction_envelope(raw)
        self.assertEqual(envelope.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
        self.assertIsNotNone(envelope.v1)
        transaction = envelope.v1.tx
        self.assertEqual(len(transaction.operations), 1)

        operation = transaction.operations[0]
        self.assertEqual(
            operation.body.op_type, xdr_codec.OPERATION_TYPE_INVOKE_HOST_FUNCTION
        )
        host_function = operation.body.invoke_host_function.host_function
        self.assertEqual(
            host_function.host_function_type,
            xdr_codec.HOST_FUNCTION_TYPE_UPLOAD_CONTRACT_WASM,
        )
        self.assertEqual(host_function.wasm, MINIMAL_WASM)
        self.assertIsNone(host_function.invoke_contract)

        # The variable-length opaque field is length-prefixed and padded; the
        # eight-byte module needs no padding, so the encoded field is exactly
        # the length prefix plus the payload.
        self.assertIn(struct.pack(">I", len(MINIMAL_WASM)) + MINIMAL_WASM, raw)
        self.assertEqual(xdr_codec.encode_transaction_envelope(envelope), raw)

    def test_evidence_record_matches_the_fixture_bytes(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(
            record["fixtureId"], "p28-xdr-transaction-envelope-upload-contract-wasm"
        )
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["outcome"], "matched")
        self.assertEqual(
            record["fixtureSha256"],
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
