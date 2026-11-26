"""Focused offline checks for the ContractCodeEntry opaque padding fixtures (issue #530).

The fixtures are synthetic structural data. They exercise an empty code vector
and a three-byte code vector with one zero padding byte, next to the existing
four-byte baseline that needs no padding.
"""
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

PACK = REPO_ROOT / "protocol-28"
IDS = (
    "p28-xdr-contract-code-opaque-padding-empty",
    "p28-xdr-contract-code-opaque-padding-three-bytes",
)
BASELINE_ID = "p28-xdr-ledger-entry-contract-code"


def load(fixture_id: str, directory: str = "campaign") -> tuple[dict, str, bytes]:
    path = PACK / "xdr" / directory / f"{fixture_id}.toml"
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


class ContractCodeOpaquePaddingFixtureTests(unittest.TestCase):
    def test_metadata_is_pinned_and_explained(self) -> None:
        for fixture_id in IDS:
            with self.subTest(fixture_id=fixture_id):
                data, text, _ = load(fixture_id)
                self.assertEqual(data["id"], fixture_id)
                self.assertEqual(data["type"], "LedgerEntry")
                self.assertEqual(data["kind"], "roundtrip")
                self.assertEqual(data["protocol"], 28)
                self.assertEqual(data["category"], "campaign")
                self.assertIn(
                    "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/Stellar-ledger-entries.x",
                    data["source_reference"],
                )
                self.assertIn("stellar-xdr 28.0.1", text)
                self.assertIn("rustc 1.98.1", text)
                self.assertIn("synthetic", text)

    def test_empty_code_decodes_and_roundtrips(self) -> None:
        _, _, raw = load(IDS[0])
        direct = xdr_codec.decode_ledger_entry(raw)
        self.assertEqual(direct, xdr_codec.decode_xdr("LedgerEntry", raw))
        self.assertEqual(direct.entry_type, xdr_codec.LEDGER_ENTRY_TYPE_CONTRACT_CODE)
        self.assertEqual(direct.last_modified_ledger_seq, 1_234_570)
        self.assertIsNotNone(direct.contract_code)
        self.assertEqual(direct.contract_code.hash, b"\x55" * 32)
        self.assertEqual(direct.contract_code.code, b"")
        self.assertEqual(len(direct.contract_code.code), 0)
        self.assertEqual(int.from_bytes(raw[44:48], "big"), 0)
        self.assertEqual(xdr_codec.encode_ledger_entry(direct), raw)
        self.assertEqual(xdr_codec.encode_xdr("LedgerEntry", direct), raw)

    def test_three_byte_code_decodes_and_roundtrips(self) -> None:
        _, _, raw = load(IDS[1])
        direct = xdr_codec.decode_ledger_entry(raw)
        self.assertEqual(direct, xdr_codec.decode_xdr("LedgerEntry", raw))
        self.assertEqual(direct.entry_type, xdr_codec.LEDGER_ENTRY_TYPE_CONTRACT_CODE)
        self.assertEqual(direct.last_modified_ledger_seq, 1_234_570)
        self.assertIsNotNone(direct.contract_code)
        self.assertEqual(direct.contract_code.hash, b"\x55" * 32)
        self.assertEqual(direct.contract_code.code, bytes.fromhex("616263"))
        self.assertEqual(len(direct.contract_code.code), 3)
        self.assertEqual(int.from_bytes(raw[44:48], "big"), 3)
        self.assertEqual(raw[48:51], b"abc")
        self.assertEqual(raw[51], 0)
        self.assertEqual(xdr_codec.encode_ledger_entry(direct), raw)
        self.assertEqual(xdr_codec.encode_xdr("LedgerEntry", direct), raw)

    def test_baseline_four_byte_code_needs_no_padding(self) -> None:
        _, _, baseline_raw = load(BASELINE_ID, directory="ledger-entry")
        entry = xdr_codec.decode_ledger_entry(baseline_raw)
        self.assertEqual(entry.contract_code.code, bytes.fromhex("0061736d"))
        self.assertEqual(int.from_bytes(baseline_raw[44:48], "big"), 4)

    def test_nonzero_padding_is_rejected_by_both_decoders(self) -> None:
        _, _, raw = load(IDS[1])
        mutated = bytearray(raw)
        mutated[51] = 1
        for name, decoder in (
            ("decode_ledger_entry", xdr_codec.decode_ledger_entry),
            ("decode_xdr", lambda value: xdr_codec.decode_xdr("LedgerEntry", value)),
        ):
            with self.subTest(decoder=name):
                with self.assertRaises(xdr_codec.XdrCodecError) as caught:
                    decoder(bytes(mutated))
                self.assertIn("non-zero padding in variable-length opaque", str(caught.exception))

    def test_evidence_records_bind_the_fixture_bytes(self) -> None:
        for fixture_id in IDS:
            with self.subTest(fixture_id=fixture_id):
                record = json.loads(
                    (PACK / "evidence" / "records" / f"{fixture_id}.json").read_text(encoding="utf-8")
                )
                fixture_bytes = (PACK / "xdr" / "campaign" / f"{fixture_id}.toml").read_bytes()
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["fixtureSha256"], hashlib.sha256(fixture_bytes).hexdigest())


if __name__ == "__main__":
    unittest.main()
