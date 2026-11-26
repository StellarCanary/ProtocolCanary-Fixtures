"""Focused offline checks for the TEMPORARY ContractDataEntry fixture (issue #528).

The fixture is synthetic structural data. It keeps the baseline symbol key and
U32 value and changes only the durability discriminant, so the test can pin the
exact field that differs as well as the crate-produced byte-for-byte roundtrip.
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

FIXTURE_ID = "p28-xdr-contract-data-temporary-temporary"
PACK = REPO_ROOT / "protocol-28"
FIXTURE = PACK / "xdr" / "campaign" / f"{FIXTURE_ID}.toml"
RECORD = PACK / "evidence" / "records" / f"{FIXTURE_ID}.json"
BASELINE = PACK / "xdr" / "ledger-entry" / "p28-xdr-ledger-entry-contract-data.toml"


def load(path: Path) -> tuple[dict, str, bytes]:
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


class ContractDataTemporaryFixtureTests(unittest.TestCase):
    def test_metadata_is_pinned_and_explained(self) -> None:
        data, text, _ = load(FIXTURE)
        self.assertEqual(data["id"], FIXTURE_ID)
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
        self.assertIn("ContractDataDurability::Temporary", text)
        self.assertIn("synthetic", text)

    def test_decoded_fields_and_exact_roundtrip(self) -> None:
        _, _, raw = load(FIXTURE)
        direct = xdr_codec.decode_ledger_entry(raw)
        generic = xdr_codec.decode_xdr("LedgerEntry", raw)
        self.assertEqual(direct, generic)

        self.assertEqual(direct.entry_type, xdr_codec.LEDGER_ENTRY_TYPE_CONTRACT_DATA)
        self.assertEqual(direct.last_modified_ledger_seq, 1_234_569)
        data = direct.contract_data
        self.assertIsNotNone(data)
        self.assertEqual(data.contract.address_type, xdr_codec.SC_ADDRESS_TYPE_CONTRACT)
        self.assertEqual(data.contract.contract_id, b"\x22" * 32)
        self.assertEqual(data.key, ("symbol", "counter"))
        self.assertEqual(data.durability, xdr_codec.CONTRACT_DATA_TEMPORARY)
        self.assertEqual(data.durability, 0)
        self.assertEqual(data.val, ("u32", 42))

        self.assertEqual(xdr_codec.encode_ledger_entry(direct), raw)
        self.assertEqual(xdr_codec.encode_xdr("LedgerEntry", direct), raw)

    def test_only_durability_differs_from_the_baseline(self) -> None:
        _, _, raw = load(FIXTURE)
        _, _, baseline_raw = load(BASELINE)
        self.assertEqual(len(raw), len(baseline_raw))
        self.assertEqual(raw[0:64], baseline_raw[0:64])
        self.assertEqual(int.from_bytes(raw[64:68], "big"), 0)
        self.assertEqual(int.from_bytes(baseline_raw[64:68], "big"), 1)
        self.assertEqual(raw[68:], baseline_raw[68:])

    def test_unknown_durability_is_rejected_by_both_decoders(self) -> None:
        _, _, raw = load(FIXTURE)
        mutated = bytearray(raw)
        mutated[64:68] = (2).to_bytes(4, "big")
        for name, decoder in (
            ("decode_ledger_entry", xdr_codec.decode_ledger_entry),
            ("decode_xdr", lambda value: xdr_codec.decode_xdr("LedgerEntry", value)),
        ):
            with self.subTest(decoder=name):
                with self.assertRaises(xdr_codec.XdrCodecError) as caught:
                    decoder(bytes(mutated))
                self.assertIn("unknown ContractDataDurability discriminant", str(caught.exception))

    def test_evidence_record_binds_the_fixture_bytes(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["fixtureSha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
