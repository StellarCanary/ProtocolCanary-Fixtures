"""Focused offline checks for AccountEntry signer arms and capacity (issue #525)."""
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
ED25519_ID = "p28-xdr-account-signers-ed25519"
PREAUTH_ID = "p28-xdr-account-signers-preauth-tx"
HASH_X_ID = "p28-xdr-account-signers-hash-x"
MAXIMUM_ID = "p28-xdr-account-signers-maximum"
OVER_LIMIT_ID = "p28-xdr-account-signers-over-limit"
SIGNER_COUNT_OFFSET = 92
SINGLE_CASES = (
    (ED25519_ID, 0, bytes([0x01]) * 32),
    (PREAUTH_ID, 1, bytes([0x02]) * 32),
    (HASH_X_ID, 2, bytes([0x03]) * 32),
)


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
    test.assertEqual(account.home_domain, "example.test")
    test.assertEqual(account.thresholds, bytes([1, 0, 0, 0]))


class AccountSignerTests(unittest.TestCase):
    def test_metadata_and_provenance(self) -> None:
        all_ids = [case[0] for case in SINGLE_CASES] + [MAXIMUM_ID, OVER_LIMIT_ID]
        for fixture_id in all_ids:
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

    def test_single_signer_arms_round_trip(self) -> None:
        for fixture_id, expected_type, expected_key in SINGLE_CASES:
            with self.subTest(fixture_id=fixture_id):
                data, _, raw = load(fixture_id)
                self.assertEqual(data["kind"], "roundtrip")
                entry = xdr_codec.decode_ledger_entry(raw)
                self.assertEqual(entry, xdr_codec.decode_xdr("LedgerEntry", raw))
                assert_baseline_account(self, entry)
                account = entry.account
                self.assertIsNotNone(account)
                self.assertEqual(len(account.signers), 1)
                signer = account.signers[0]
                self.assertEqual(signer.key_type, expected_type)
                self.assertEqual(signer.key, expected_key)
                self.assertEqual(len(signer.key), 32)
                self.assertEqual(signer.weight, 1)
                self.assertEqual(raw, xdr_codec.encode_ledger_entry(entry))
                self.assertEqual(raw, xdr_codec.encode_xdr("LedgerEntry", entry))

    def test_maximum_twenty_signer_vector_round_trips(self) -> None:
        data, _, raw = load(MAXIMUM_ID)
        self.assertEqual(data["kind"], "roundtrip")
        entry = xdr_codec.decode_ledger_entry(raw)
        self.assertEqual(entry, xdr_codec.decode_xdr("LedgerEntry", raw))
        assert_baseline_account(self, entry)
        account = entry.account
        self.assertIsNotNone(account)
        self.assertEqual(len(account.signers), 20)
        self.assertEqual([signer.key_type for signer in account.signers], [0] * 20)
        self.assertEqual([signer.weight for signer in account.signers], [1] * 20)
        self.assertEqual(account.signers[0].key, bytes([0x01]) * 32)
        self.assertEqual(account.signers[19].key, bytes([0x14]) * 32)
        self.assertEqual(len({signer.key for signer in account.signers}), 20)
        self.assertTrue(all(len(signer.key) == 32 for signer in account.signers))
        self.assertEqual(raw, xdr_codec.encode_ledger_entry(entry))
        self.assertEqual(raw, xdr_codec.encode_xdr("LedgerEntry", entry))

    def test_over_limit_signer_vector_is_a_documented_mutation(self) -> None:
        data, text, raw = load(OVER_LIMIT_ID)
        self.assertEqual(data["kind"], "decode-failure")
        self.assertIn("byte offset 92", text)
        self.assertEqual(
            struct.unpack(">I", raw[SIGNER_COUNT_OFFSET:SIGNER_COUNT_OFFSET + 4])[0], 21
        )

        _, _, maximum_raw = load(MAXIMUM_ID)
        self.assertEqual(
            struct.unpack(">I", maximum_raw[SIGNER_COUNT_OFFSET:SIGNER_COUNT_OFFSET + 4])[0], 20
        )
        self.assertEqual(
            maximum_raw[:SIGNER_COUNT_OFFSET] + (21).to_bytes(4, "big")
            + maximum_raw[SIGNER_COUNT_OFFSET + 4:],
            raw,
        )

        for decoder in (
            xdr_codec.decode_ledger_entry,
            lambda value: xdr_codec.decode_xdr("LedgerEntry", value),
        ):
            with self.subTest(decoder=decoder), self.assertRaisesRegex(
                xdr_codec.XdrCodecError, "signers length prefix 21 exceeds maximum 20"
            ):
                decoder(raw)

    def test_evidence_records_bind_the_fixture_bytes(self) -> None:
        all_ids = [case[0] for case in SINGLE_CASES] + [MAXIMUM_ID, OVER_LIMIT_ID]
        for fixture_id in all_ids:
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
