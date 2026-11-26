"""Focused offline checks for the symbol-value ContractDataEntry fixture (issue #529).

The fixture is synthetic structural data. It places an SCV_U32 key at 7 and a
nonempty SCV_SYMBOL value, exercising the reciprocal of the baseline key/value
layout and the length and padding at the value position.
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

FIXTURE_ID = "p28-xdr-contract-data-value-symbol-symbol-value"
PACK = REPO_ROOT / "protocol-28"
FIXTURE = PACK / "xdr" / "campaign" / f"{FIXTURE_ID}.toml"
RECORD = PACK / "evidence" / "records" / f"{FIXTURE_ID}.json"
BASELINE = PACK / "xdr" / "ledger-entry" / "p28-xdr-ledger-entry-contract-data.toml"


def load(path: Path) -> tuple[dict, str, bytes]:
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


class ContractDataValueSymbolFixtureTests(unittest.TestCase):
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
        self.assertIn("ScVal::U32(7)", text)
        self.assertIn("ScVal::Symbol", text)
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
        self.assertEqual(data.key, ("u32", 7))
        self.assertEqual(data.durability, xdr_codec.CONTRACT_DATA_PERSISTENT)
        self.assertEqual(data.val, ("symbol", "key"))

        self.assertEqual(xdr_codec.encode_ledger_entry(direct), raw)
        self.assertEqual(xdr_codec.encode_xdr("LedgerEntry", direct), raw)

    def test_key_and_value_discriminants_are_independent(self) -> None:
        _, _, raw = load(FIXTURE)
        _, _, baseline_raw = load(BASELINE)
        self.assertEqual(int.from_bytes(raw[48:52], "big"), xdr_codec.SCV_U32)
        self.assertEqual(int.from_bytes(raw[52:56], "big"), 7)
        self.assertEqual(int.from_bytes(raw[60:64], "big"), xdr_codec.SCV_SYMBOL)
        self.assertEqual(int.from_bytes(raw[64:68], "big"), 3)
        self.assertEqual(raw[68:71], b"key")
        self.assertEqual(raw[71], 0)
        baseline = xdr_codec.decode_ledger_entry(baseline_raw).contract_data
        self.assertEqual(baseline.key, ("symbol", "counter"))
        self.assertEqual(baseline.val, ("u32", 42))

    def test_unknown_value_discriminant_is_rejected_by_both_decoders(self) -> None:
        _, _, raw = load(FIXTURE)
        mutated = bytearray(raw)
        mutated[60:64] = (0).to_bytes(4, "big")
        for name, decoder in (
            ("decode_ledger_entry", xdr_codec.decode_ledger_entry),
            ("decode_xdr", lambda value: xdr_codec.decode_xdr("LedgerEntry", value)),
        ):
            with self.subTest(decoder=name):
                with self.assertRaises(xdr_codec.XdrCodecError) as caught:
                    decoder(bytes(mutated))
                self.assertIn("unsupported ScVal discriminant", str(caught.exception))

    def test_evidence_record_binds_the_fixture_bytes(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["fixtureSha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
