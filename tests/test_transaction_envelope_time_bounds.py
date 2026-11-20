"""Offline checks for the Protocol 28 PRECOND_TIME envelope fixture.

The fixture is synthetic structural data. It asserts the field order and
uint64 encoding of the two time bounds; it does not claim the transaction is
valid for any current ledger time or was ever submitted.
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
    / "p28-xdr-transaction-envelope-time-bounds.toml"
)
RECORD = (
    REPO_ROOT
    / "protocol-28"
    / "evidence"
    / "records"
    / "p28-xdr-transaction-envelope-time-bounds.json"
)
MIN_TIME = 1_700_000_000
MAX_TIME = 1_700_086_400


def load_fixture() -> dict:
    with FIXTURE.open("rb") as handle:
        return tomllib.load(handle)


class TimeBoundsEnvelopeTests(unittest.TestCase):
    def test_fixture_metadata_and_pinned_source(self) -> None:
        fixture = load_fixture()
        self.assertEqual(fixture["id"], "p28-xdr-transaction-envelope-time-bounds")
        self.assertEqual(fixture["protocol"], 28)
        self.assertEqual(fixture["surface"], "xdr")
        self.assertEqual(fixture["category"], "transaction-envelope")
        self.assertEqual(fixture["type"], "TransactionEnvelope")
        self.assertEqual(fixture["kind"], "roundtrip")
        self.assertIn(
            "9c9c145953e80990d6ff1ae3a6a973a0ce6d0694",
            fixture["source_reference"],
        )

    def test_precond_time_roundtrips_with_increasing_uint64_bounds(self) -> None:
        fixture = load_fixture()
        raw = base64.b64decode(fixture["value_base64"], validate=True)
        self.assertEqual(len(raw), 216)

        envelope = xdr_codec.decode_transaction_envelope(raw)
        self.assertEqual(envelope.envelope_type, xdr_codec.ENVELOPE_TYPE_TX)
        transaction = envelope.v1.tx
        self.assertEqual(transaction.cond.precond_type, xdr_codec.PRECOND_TIME)
        self.assertIsNotNone(transaction.cond.time_bounds)
        bounds = transaction.cond.time_bounds
        self.assertEqual(bounds.min_time, MIN_TIME)
        self.assertEqual(bounds.max_time, MAX_TIME)
        self.assertLess(bounds.min_time, bounds.max_time)

        encoded_bounds = struct.pack(">QQ", MIN_TIME, MAX_TIME)
        first = raw.find(encoded_bounds)
        self.assertGreaterEqual(first, 0)
        self.assertEqual(raw.find(encoded_bounds, first + 1), -1)
        self.assertEqual(xdr_codec.encode_transaction_envelope(envelope), raw)

    def test_evidence_record_matches_the_fixture_bytes(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(
            record["fixtureId"], "p28-xdr-transaction-envelope-time-bounds"
        )
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["outcome"], "matched")
        self.assertEqual(
            record["fixtureSha256"],
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
