"""Focused offline checks for AccountEntry homeDomain length bounds (issue #524)."""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import xdr_codec  # noqa: E402

PACK = REPO_ROOT / "protocol-28"
FIXTURES = PACK / "xdr" / "campaign"
RECORDS = PACK / "evidence" / "records"
EMPTY_ID = "p28-xdr-account-home-domain-bounds-empty"
MAXIMUM_ID = "p28-xdr-account-home-domain-bounds-maximum"
OVER_LIMIT_ID = "p28-xdr-account-home-domain-bounds-over-limit"
MAX_HOME = bytes.fromhex("61" * 32)
HOME_LENGTH_OFFSET = 72


def load(fixture_id: str) -> tuple[dict, str, bytes]:
    path = FIXTURES / f"{fixture_id}.toml"
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


def assert_baseline_account(test: unittest.TestCase, entry: xdr_codec.LedgerEntry) -> None:
    test.assertEqual(entry.last_modified_ledger_seq, 1_234_567)
    test.assertEqual(entry.entry_type, xdr_codec.LEDGER_ENTRY_TYPE_ACCOUNT)
    account = entry.account
    test.assertIsNotNone(account)
    test.assertEqual(account.account_id.ed25519, bytes([0x11]) * 32)
    test.assertEqual(account.balance, 100_000_000)
    test.assertEqual(account.seq_num, 42)
    test.assertEqual(account.num_sub_entries, 0)
    test.assertIsNone(account.inflation_dest)
    test.assertEqual(account.flags, 0)
    test.assertEqual(account.thresholds, bytes([1, 0, 0, 0]))
    test.assertEqual(account.signers, ())


class AccountHomeDomainBoundsTests(unittest.TestCase):
    def test_metadata_and_provenance(self) -> None:
        for fixture_id in (EMPTY_ID, MAXIMUM_ID, OVER_LIMIT_ID):
            with self.subTest(fixture_id=fixture_id):
                data, text, _ = load(fixture_id)
                self.assertEqual(data["id"], fixture_id)
                self.assertEqual(data["protocol"], 28)
                self.assertEqual(data["surface"], "xdr")
                self.assertEqual(data["category"], "campaign")
                self.assertEqual(data["type"], "LedgerEntry")
                self.assertIn(
                    "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/Stellar-ledger-entries.x",
                    data["source_reference"],
                )
                self.assertIn("stellar-xdr 28.0.1", text)
                self.assertIn("synthetic", text.lower())

    def test_empty_home_domain_round_trips(self) -> None:
        data, _, raw = load(EMPTY_ID)
        self.assertEqual(data["kind"], "roundtrip")
        entry = xdr_codec.decode_ledger_entry(raw)
        self.assertEqual(entry, xdr_codec.decode_xdr("LedgerEntry", raw))
        assert_baseline_account(self, entry)
        account = entry.account
        self.assertIsNotNone(account)
        self.assertEqual(account.home_domain.encode("utf-8"), b"")
        self.assertEqual(raw, xdr_codec.encode_ledger_entry(entry))
        self.assertEqual(raw, xdr_codec.encode_xdr("LedgerEntry", entry))

    def test_maximum_home_domain_round_trips(self) -> None:
        data, _, raw = load(MAXIMUM_ID)
        self.assertEqual(data["kind"], "roundtrip")
        entry = xdr_codec.decode_ledger_entry(raw)
        self.assertEqual(entry, xdr_codec.decode_xdr("LedgerEntry", raw))
        assert_baseline_account(self, entry)
        account = entry.account
        self.assertIsNotNone(account)
        home = account.home_domain.encode("utf-8")
        self.assertEqual(home, MAX_HOME)
        self.assertEqual(len(home), 32)
        self.assertEqual(home.hex(), "61" * 32)
        self.assertEqual(raw, xdr_codec.encode_ledger_entry(entry))
        self.assertEqual(raw, xdr_codec.encode_xdr("LedgerEntry", entry))

    def test_over_limit_home_domain_is_a_documented_mutation(self) -> None:
        data, text, raw = load(OVER_LIMIT_ID)
        self.assertEqual(data["kind"], "decode-failure")
        self.assertIn("byte offset 72", text)
        self.assertEqual(struct.unpack(">I", raw[HOME_LENGTH_OFFSET:HOME_LENGTH_OFFSET + 4])[0], 33)

        _, _, maximum_raw = load(MAXIMUM_ID)
        self.assertEqual(
            struct.unpack(">I", maximum_raw[HOME_LENGTH_OFFSET:HOME_LENGTH_OFFSET + 4])[0], 32
        )
        self.assertEqual(
            maximum_raw[:HOME_LENGTH_OFFSET] + (33).to_bytes(4, "big")
            + maximum_raw[HOME_LENGTH_OFFSET + 4:],
            raw,
        )

        for decoder in (
            xdr_codec.decode_ledger_entry,
            lambda value: xdr_codec.decode_xdr("LedgerEntry", value),
        ):
            with self.subTest(decoder=decoder), self.assertRaisesRegex(
                xdr_codec.XdrCodecError, "length prefix 33 exceeds maximum allowed 32"
            ):
                decoder(raw)

    def test_evidence_records_bind_the_fixture_bytes(self) -> None:
        for fixture_id in (EMPTY_ID, MAXIMUM_ID, OVER_LIMIT_ID):
            with self.subTest(fixture_id=fixture_id):
                record = json.loads((RECORDS / f"{fixture_id}.json").read_text(encoding="utf-8"))
                fixture_path = FIXTURES / f"{fixture_id}.toml"
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["outcome"], "matched")
                self.assertEqual(
                    record["fixtureSha256"], hashlib.sha256(fixture_path.read_bytes()).hexdigest()
                )


if __name__ == "__main__":
    unittest.main()
