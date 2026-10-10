"""Tests for schemas/registry-v1.schema.json (F-002, CF-02 section 3).

Run with: python3 -m unittest discover tests
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((REPO_ROOT / "schemas" / "registry-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)

SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

MANIFEST = {
    "registryVersion": 1,
    "protocol": 28,
    "fixtures": [
        {
            "id": "p28-xdr-cap85-external-ref-roundtrip",
            "path": "protocol-28/xdr/cap-0085/p28-xdr-cap85-external-ref-roundtrip.toml",
            "sha256": SHA,
            "surface": "xdr",
            "category": "cap-0085",
            "description": "CAP-0085 round-trip fixture",
            "payloads": [{"path": "payloads/a.bin", "sha256": SHA}],
            "sourceReference": "https://github.com/stellar/stellar-protocol/blob/master/core/cap-0085.md",
            "requiredCapabilities": ["stellar-sdk-dependency"],
        }
    ],
    "packDigest": f"sha256:{SHA}",
}


class RegistrySchemaTest(unittest.TestCase):
    def test_conforming_manifest_validates(self) -> None:
        VALIDATOR.validate(MANIFEST)

    def test_optional_fields_may_be_omitted(self) -> None:
        record = copy.deepcopy(MANIFEST)
        del record["fixtures"][0]["sourceReference"]
        del record["fixtures"][0]["requiredCapabilities"]
        VALIDATOR.validate(record)

    def test_bad_digest_rejected(self) -> None:
        record = copy.deepcopy(MANIFEST)
        record["packDigest"] = SHA
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)

    def test_missing_required_field_rejected(self) -> None:
        record = copy.deepcopy(MANIFEST)
        del record["fixtures"]
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)

    def test_unsupported_version_rejected(self) -> None:
        record = copy.deepcopy(MANIFEST)
        record["registryVersion"] = 2
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)

    def test_undeclared_property_rejected(self) -> None:
        record = copy.deepcopy(MANIFEST)
        record["fixtures"][0]["bogus"] = 1
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)


if __name__ == "__main__":
    unittest.main()
