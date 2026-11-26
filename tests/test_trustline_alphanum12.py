"""Focused offline checks for the AlphaNum12 TrustLineAsset fixture (issue #526).

The fixture is synthetic structural data. It asserts the 2-byte asset-type
discriminant, the fixed 12-byte code and the issuer key that follows it, then
requires the independent codec to reproduce the crate-produced bytes exactly.
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

FIXTURE_ID = "p28-xdr-trustline-alphanum12-alphanum12"
PACK = REPO_ROOT / "protocol-28"
FIXTURE = PACK / "xdr" / "campaign" / f"{FIXTURE_ID}.toml"
RECORD = PACK / "evidence" / "records" / f"{FIXTURE_ID}.json"
BASELINE = PACK / "xdr" / "ledger-entry" / "p28-xdr-ledger-entry-trustline.toml"


def load(path: Path) -> tuple[dict, str, bytes]:
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


class TrustLineAlphaNum12FixtureTests(unittest.TestCase):
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
        self.assertIn("AssetCode12(*b\"ABCDEFGHIJKL\")", text)
        self.assertIn("synthetic", text)

    def test_decoded_fields_and_exact_roundtrip(self) -> None:
        _, _, raw = load(FIXTURE)
        direct = xdr_codec.decode_ledger_entry(raw)
        generic = xdr_codec.decode_xdr("LedgerEntry", raw)
        self.assertEqual(direct, generic)

        self.assertEqual(direct.entry_type, xdr_codec.LEDGER_ENTRY_TYPE_TRUSTLINE)
        self.assertEqual(direct.last_modified_ledger_seq, 1_234_568)
        trustline = direct.trustline
        self.assertIsNotNone(trustline)
        self.assertEqual(trustline.account_id.ed25519, b"\x33" * 32)
        self.assertEqual(trustline.asset.asset_type, xdr_codec.ASSET_TYPE_CREDIT_ALPHANUM12)
        self.assertEqual(trustline.asset.asset_type, 2)
        self.assertEqual(trustline.asset.alpha_num4, None)
        self.assertIsNotNone(trustline.asset.alpha_num12)
        self.assertEqual(trustline.asset.alpha_num12.asset_code, b"ABCDEFGHIJKL")
        self.assertEqual(len(trustline.asset.alpha_num12.asset_code), 12)
        self.assertEqual(trustline.asset.alpha_num12.issuer.ed25519, b"\x44" * 32)
        self.assertEqual(trustline.balance, 25_000_000)
        self.assertEqual(trustline.limit, 2**63 - 1)
        self.assertEqual(trustline.flags, 1)

        self.assertEqual(xdr_codec.encode_ledger_entry(direct), raw)
        self.assertEqual(xdr_codec.encode_xdr("LedgerEntry", direct), raw)

    def test_asset_code_precedes_issuer_on_the_wire(self) -> None:
        _, _, raw = load(FIXTURE)
        self.assertEqual(int.from_bytes(raw[44:48], "big"), 2)
        self.assertEqual(raw[48:60], b"ABCDEFGHIJKL")
        self.assertEqual(int.from_bytes(raw[60:64], "big", signed=True), 0)
        self.assertEqual(raw[64:96], b"\x44" * 32)

    def test_only_the_asset_arm_differs_from_the_alpha_num4_baseline(self) -> None:
        _, _, raw = load(FIXTURE)
        _, _, baseline_raw = load(BASELINE)
        self.assertEqual(raw[0:44], baseline_raw[0:44])
        self.assertNotEqual(raw[44:96], baseline_raw[44:88])
        self.assertEqual(raw[96:], baseline_raw[88:])

    def test_unknown_asset_type_is_rejected_by_both_decoders(self) -> None:
        _, _, raw = load(FIXTURE)
        mutated = bytearray(raw)
        mutated[44:48] = (4).to_bytes(4, "big")
        for name, decoder in (
            ("decode_ledger_entry", xdr_codec.decode_ledger_entry),
            ("decode_xdr", lambda value: xdr_codec.decode_xdr("LedgerEntry", value)),
        ):
            with self.subTest(decoder=name):
                with self.assertRaises(xdr_codec.XdrCodecError) as caught:
                    decoder(bytes(mutated))
                self.assertIn("unknown TrustLineAssetType discriminant", str(caught.exception))

    def test_evidence_record_binds_the_fixture_bytes(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["fixtureSha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
