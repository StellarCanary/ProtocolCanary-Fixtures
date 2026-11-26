"""Focused offline checks for an account owner in CAP-0085 ExternalRef (issue #537)."""
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

CAMPAIGN = REPO_ROOT / "protocol-28" / "xdr" / "campaign"
CAP_0085 = REPO_ROOT / "protocol-28" / "xdr" / "cap-0085"
RECORDS = REPO_ROOT / "protocol-28" / "evidence" / "records"
BASELINE_ID = "p28-xdr-cap85-external-ref-roundtrip"
FIXTURE_ID = "p28-xdr-external-ref-account-owner-account"


def load_fixture() -> tuple[dict, bytes, Path]:
    path = CAMPAIGN / f"{FIXTURE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


def load_baseline() -> tuple[dict, bytes, Path]:
    path = CAP_0085 / f"{BASELINE_ID}.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True), path


class ExternalRefAccountOwnerTests(unittest.TestCase):
    def test_fixture_metadata_is_pinned(self) -> None:
        data, _, path = load_fixture()
        self.assertEqual(data["id"], FIXTURE_ID)
        self.assertEqual(data["protocol"], 28)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["type"], "ContractExecutable")
        self.assertEqual(data["kind"], "roundtrip")
        self.assertIn("/blob/9c9c145953e80990d6ff1ae3a6a973a0ce6d0694/", data["source_reference"])
        header = path.read_text(encoding="utf-8")
        self.assertIn("`stellar-xdr` 28.0.1", header)
        self.assertIn("ScAddress::Account", header)

    def test_executable_owner_is_the_account_composite_layout(self) -> None:
        _, raw, _ = load_fixture()
        decoded = xdr_codec.decode_contract_executable(raw)
        generic = xdr_codec.decode_xdr("ContractExecutable", raw)
        self.assertEqual(decoded, generic)
        self.assertEqual(decoded.executable_type, xdr_codec.CONTRACT_EXECUTABLE_EXTERNAL_REF)
        self.assertIsNotNone(decoded.external_ref)
        owner = decoded.external_ref.executable_owner
        self.assertEqual(owner.address_type, xdr_codec.SC_ADDRESS_TYPE_ACCOUNT)
        self.assertIsNotNone(owner.account_id)
        self.assertEqual(owner.account_id.key_type, xdr_codec.PUBLIC_KEY_TYPE_ED25519)
        self.assertEqual(owner.account_id.ed25519, b"\x66" * 32)
        self.assertEqual(len(owner.account_id.ed25519), 32)
        self.assertEqual(decoded.external_ref.tag, "fleet-v1")
        self.assertEqual(raw[4:8], (0).to_bytes(4, "big"))
        self.assertEqual(raw[8:12], (0).to_bytes(4, "big"))
        self.assertEqual(raw[12:44], b"\x66" * 32)

    def test_only_owner_layout_differs_from_baseline(self) -> None:
        _, raw, _ = load_fixture()
        _, baseline_raw, _ = load_baseline()
        decoded = xdr_codec.decode_contract_executable(raw)
        baseline = xdr_codec.decode_contract_executable(baseline_raw)
        self.assertEqual(decoded.external_ref.tag, baseline.external_ref.tag)
        self.assertEqual(
            baseline.external_ref.executable_owner.address_type,
            xdr_codec.SC_ADDRESS_TYPE_CONTRACT,
        )
        self.assertNotEqual(
            decoded.external_ref.executable_owner.address_type,
            baseline.external_ref.executable_owner.address_type,
        )
        self.assertEqual(len(raw) - len(baseline_raw), 4)

    def test_exact_roundtrip_with_both_codec_interfaces(self) -> None:
        _, raw, _ = load_fixture()
        decoded = xdr_codec.decode_contract_executable(raw)
        self.assertEqual(xdr_codec.encode_contract_executable(decoded), raw)
        self.assertEqual(xdr_codec.encode_xdr("ContractExecutable", decoded), raw)

    def test_structural_record_binds_the_fixture_bytes(self) -> None:
        _, _, path = load_fixture()
        record = json.loads((RECORDS / f"{FIXTURE_ID}.json").read_text(encoding="utf-8"))
        self.assertEqual(record["fixtureId"], FIXTURE_ID)
        self.assertEqual(record["method"], "structural")
        self.assertEqual(record["fixtureSha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
