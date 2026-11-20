"""Focused offline checks for the corrected Protocol 28 ScVal schema fixtures.

These tests pin the layouts corrected for issue #503: the SCError
discriminants, SCContractInstance.storage as an SCMap pointer, SCNonceKey as a
signed int64, SCV_EXECUTABLE_TAG as an SCString, and the v28.0 SCAddress arms
for muxed accounts, claimable balances and liquidity pools.

Everything here is structural and offline. Claimable-balance, liquidity-pool,
internal ledger-key and executable-tag values are not claimed to be accepted by
the Soroban host.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK = REPO_ROOT / "protocol-28"
CODEC_PATH = REPO_ROOT / "tests" / "scval_xdr.py"

_spec = importlib.util.spec_from_file_location("scval_xdr", CODEC_PATH)
assert _spec is not None and _spec.loader is not None
scval_xdr = importlib.util.module_from_spec(_spec)
sys.modules["scval_xdr"] = scval_xdr
_spec.loader.exec_module(scval_xdr)

FIXTURES = {
    "p28-xdr-scval-address-muxed-account": (
        "xdr/scval-composite/p28-xdr-scval-address-muxed-account.toml",
        {
            "type": "address",
            "value": {
                "type": "muxed-account",
                "id": 0x0102030405060708,
                "ed25519": "33" * 32,
            },
        },
    ),
    "p28-xdr-scval-address-claimable-balance": (
        "xdr/scval-composite/p28-xdr-scval-address-claimable-balance.toml",
        {
            "type": "address",
            "value": {
                "type": "claimable-balance",
                "balance_id": {"type": "v0", "hash": "44" * 32},
            },
        },
    ),
    "p28-xdr-scval-address-liquidity-pool": (
        "xdr/scval-composite/p28-xdr-scval-address-liquidity-pool.toml",
        {
            "type": "address",
            "value": {"type": "liquidity-pool", "pool_id": "55" * 32},
        },
    ),
    "p28-xdr-scval-error-value": (
        "xdr/scval/p28-xdr-scval-error-value.toml",
        {"type": "error", "value": {"type": "contract", "code": 100}},
    ),
    "p28-xdr-scval-contract-instance-storage-map": (
        "xdr/scval-composite/p28-xdr-scval-contract-instance-storage-map.toml",
        {
            "type": "contract-instance",
            "value": {
                "executable": {"type": "wasm", "wasm_hash": "ab" * 32},
                "storage": [
                    {
                        "key": {"type": "symbol", "value": "a"},
                        "val": {"type": "u32", "value": 7},
                    }
                ],
            },
        },
    ),
    "p28-xdr-scval-ledger-key-contract-instance": (
        "xdr/scval/p28-xdr-scval-ledger-key-contract-instance.toml",
        {"type": "ledger-key-contract-instance", "value": None},
    ),
    "p28-xdr-scval-ledger-key-nonce-signed": (
        "xdr/scval/p28-xdr-scval-ledger-key-nonce-signed.toml",
        {"type": "ledger-key-nonce", "value": {"nonce": -1}},
    ),
    "p28-xdr-scval-executable-tag-string": (
        "xdr/scval/p28-xdr-scval-executable-tag-string.toml",
        {"type": "executable-tag", "value": "fleet-v1"},
    ),
}

STRUCTURAL_HEADER_IDS = {
    "p28-xdr-scval-address-claimable-balance",
    "p28-xdr-scval-address-liquidity-pool",
    "p28-xdr-scval-ledger-key-contract-instance",
    "p28-xdr-scval-ledger-key-nonce-signed",
    "p28-xdr-scval-executable-tag-string",
}


class ScValV28SchemaFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = {}
        for fixture_id, (relative, expected) in FIXTURES.items():
            path = PACK / relative
            text = path.read_text(encoding="utf-8")
            data = tomllib.loads(text)
            raw = base64.b64decode(data["value_base64"], validate=True)
            cls.loaded[fixture_id] = (path, text, data, raw, expected)

    def test_fixture_ids_and_paths_are_unique_and_pinned(self) -> None:
        self.assertEqual(len(FIXTURES), len(set(FIXTURES)))
        for fixture_id, (path, _text, data, _raw, _expected) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertEqual(data["id"], fixture_id)
                self.assertEqual(data["protocol"], 28)
                self.assertEqual(data["surface"], "xdr")
                self.assertEqual(data["type"], "ScVal")
                self.assertEqual(data["kind"], "roundtrip")
                self.assertIn(
                    "/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/",
                    data["source_reference"],
                )
                self.assertTrue(path.is_file())

    def test_headers_explain_how_expected_bytes_were_obtained(self) -> None:
        for fixture_id, (_path, text, _data, _raw, _expected) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                self.assertIn("stellar-xdr 28.0.1", text)
                self.assertIn("to_xdr_base64(Limits::none())", text)
                self.assertIn("expression, recorded verbatim", text)
                self.assertIn("generated 2026-11-20 (UTC)", text)

    def test_corrected_layouts_decode_and_round_trip(self) -> None:
        for fixture_id, (_path, _text, _data, raw, expected) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                decoded = scval_xdr.decode(raw)
                self.assertEqual(scval_xdr.to_json(decoded), expected)
                self.assertEqual(scval_xdr.encode(scval_xdr.from_json(expected)), raw)
                self.assertEqual(scval_xdr.encode(decoded), raw)

    def test_error_discriminant_zero_is_contract_not_ok(self) -> None:
        raw = self.loaded["p28-xdr-scval-error-value"][3]
        self.assertEqual(int.from_bytes(raw[4:8], "big"), scval_xdr.SCE_CONTRACT)
        self.assertEqual(
            scval_xdr.decode(raw),
            ("error", {"type": "contract", "code": 100}),
        )
        with self.assertRaises(scval_xdr.XdrEncodeError):
            scval_xdr.encode(("error", {"type": "ok"}))
        with self.assertRaises(scval_xdr.XdrEncodeError):
            scval_xdr.encode(("error", {"type": "wasm-vm", "code": 42}))

    def test_contract_instance_storage_is_an_scmap_pointer(self) -> None:
        raw = self.loaded["p28-xdr-scval-contract-instance-storage-map"][3]
        decoded = scval_xdr.decode(raw)
        self.assertEqual(decoded[0], "contract-instance")
        self.assertIsInstance(decoded[1]["storage"], list)
        self.assertEqual(decoded[1]["storage"], [(("symbol", "a"), ("u32", 7))])
        with self.assertRaises(scval_xdr.XdrEncodeError):
            scval_xdr.encode(
                (
                    "contract-instance",
                    {
                        "executable": {"type": "stellar-asset"},
                        "storage": {"type": "stellar-asset"},
                    },
                )
            )

    def test_nonce_key_is_a_single_signed_int64(self) -> None:
        raw = self.loaded["p28-xdr-scval-ledger-key-nonce-signed"][3]
        self.assertEqual(len(raw), 12)
        self.assertEqual(raw[4:], b"\xff" * 8)
        self.assertEqual(
            scval_xdr.decode(raw),
            ("ledger-key-nonce", {"nonce": -1}),
        )
        old_address_prefixed = bytes.fromhex(
            "00000015"
            "00000001" + "55" * 32
            + "000000000000002a"
        )
        with self.assertRaises(scval_xdr.XdrDecodeError):
            scval_xdr.decode(old_address_prefixed)

    def test_executable_tag_is_a_string(self) -> None:
        raw = self.loaded["p28-xdr-scval-executable-tag-string"][3]
        self.assertEqual(int.from_bytes(raw[4:8], "big"), 8)
        self.assertEqual(scval_xdr.decode(raw), ("executable-tag", "fleet-v1"))
        with self.assertRaises(scval_xdr.XdrEncodeError):
            scval_xdr.encode(
                (
                    "executable-tag",
                    {"type": "wasm", "wasm_hash": "ab" * 32},
                )
            )

    def test_v28_address_arms_are_decoded_by_discriminant(self) -> None:
        for fixture_id, address_type in (
            ("p28-xdr-scval-address-muxed-account", 2),
            ("p28-xdr-scval-address-claimable-balance", 3),
            ("p28-xdr-scval-address-liquidity-pool", 4),
        ):
            with self.subTest(fixture_id=fixture_id):
                raw = self.loaded[fixture_id][3]
                self.assertEqual(int.from_bytes(raw[4:8], "big"), address_type)
                self.assertEqual(scval_xdr.decode(raw)[0], "address")

    def test_structural_values_are_not_presented_as_host_accepted(self) -> None:
        for fixture_id in STRUCTURAL_HEADER_IDS:
            with self.subTest(fixture_id=fixture_id):
                text = self.loaded[fixture_id][1]
                self.assertIn("structural", text.lower())
                self.assertNotIn("host accepts this", text.lower())

    def test_evidence_records_bind_the_fixture_bytes(self) -> None:
        for fixture_id, (path, _text, _data, _raw, _expected) in self.loaded.items():
            with self.subTest(fixture_id=fixture_id):
                record_path = PACK / "evidence" / "records" / f"{fixture_id}.json"
                record = json.loads(record_path.read_text(encoding="utf-8"))
                self.assertEqual(record["fixtureId"], fixture_id)
                self.assertEqual(record["method"], "structural")
                self.assertEqual(record["outcome"], "matched")
                self.assertEqual(
                    record["fixtureSha256"],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )


if __name__ == "__main__":
    unittest.main()
