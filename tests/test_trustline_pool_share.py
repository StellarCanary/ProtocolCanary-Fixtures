"""Focused offline checks for the pool-share TrustLineAsset fixture (issue #527)."""
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
FIXTURE_ID = "p28-xdr-trustline-pool-share-pool-share"
FIXTURE_PATH = PACK / "xdr" / "campaign" / f"{FIXTURE_ID}.toml"
RECORD_PATH = PACK / "evidence" / "records" / f"{FIXTURE_ID}.json"


def load() -> tuple[dict, str, bytes]:
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    return data, text, base64.b64decode(data["value_base64"], validate=True)


class TrustLinePoolShareTests(unittest.TestCase):
    def test_metadata_and_provenance(self) -> None:
        data, text, _ = load()
        self.assertEqual(data["id"], FIXTURE_ID)
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "campaign")
        self.assertEqual(data["type"], "LedgerEntry")
        self.assertEqual(data["kind"], "roundtrip")
        self.assertIn(
            "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/Stellar-ledger-entries.x",
            data["source_reference"],
        )
        self.assertIn("stellar-xdr 28.0.1", text)
        self.assertIn("PoolShare", text)
        self.assertIn("synthetic", text.lower())

    def test_pool_share_asset_round_trips(self) -> None:
        _, _, raw = load()
        entry = xdr_codec.decode_ledger_entry(raw)
        self.assertEqual(entry, xdr_codec.decode_xdr("LedgerEntry", raw))
        self.assertEqual(entry.last_modified_ledger_seq, 1_234_568)
        self.assertEqual(entry.entry_type, xdr_codec.LEDGER_ENTRY_TYPE_TRUSTLINE)
        trustline = entry.trustline
        self.assertIsNotNone(trustline)
        self.assertEqual(trustline.account_id.ed25519, bytes([0x33]) * 32)
        self.assertEqual(trustline.asset.asset_type, 3)
        self.assertEqual(trustline.asset.asset_type, xdr_codec.ASSET_TYPE_POOL_SHARE)
        self.assertIsNone(trustline.asset.alpha_num4)
        self.assertIsNone(trustline.asset.alpha_num12)
        self.assertEqual(trustline.asset.pool_id, bytes([0x77]) * 32)
        self.assertEqual(len(trustline.asset.pool_id), 32)
        self.assertEqual(trustline.balance, 25_000_000)
        self.assertEqual(trustline.limit, (1 << 63) - 1)
        self.assertEqual(trustline.flags, 1)
        self.assertEqual(raw, xdr_codec.encode_ledger_entry(entry))
        self.assertEqual(raw, xdr_codec.encode_xdr("LedgerEntry", entry))

    def test_evidence_record_binds_the_fixture_bytes(self) -> None:
        record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["outcome"], "matched")
        self.assertEqual(
            record["fixtureSha256"], hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
        )


if __name__ == "__main__":
    unittest.main()
