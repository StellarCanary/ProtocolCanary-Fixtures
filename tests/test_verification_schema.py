"""Tests for schemas/verification-v1.schema.json (F-015, CF-04 section 3).

Run with: python3 -m unittest discover tests
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((REPO_ROOT / "schemas" / "verification-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

LIVE_RECORD = {
    "verificationVersion": 1,
    "fixtureId": "p29-rpc-obs-latest-ledger",
    "fixtureSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "method": "live-read-only",
    "checkedAt": "2026-10-10T04:00:00Z",
    "verifier": {"name": "protocol-canary", "version": "0.3.0"},
    "outcome": "matched",
    "network": {
        "name": "testnet",
        "passphrase": "Test SDF Network ; September 2015",
        "observedProtocol": 29,
    },
    "endpointHost": "horizon-testnet.stellar.org",
    "evidenceRef": "protocol-29/rpc/p29-rpc-latest-ledger.toml",
}

OFFLINE_RECORD = {
    "verificationVersion": 1,
    "fixtureId": "p28-xdr-cap85-external-ref-roundtrip",
    "fixtureSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "method": "structural",
    "checkedAt": "2026-10-10T04:00:00Z",
    "verifier": {"name": "protocol-canary", "version": "0.3.0"},
    "outcome": "matched",
    "network": None,
}


class VerificationSchemaTest(unittest.TestCase):
    def test_live_record_validates(self) -> None:
        VALIDATOR.validate(LIVE_RECORD)

    def test_offline_record_with_null_network_validates(self) -> None:
        VALIDATOR.validate(OFFLINE_RECORD)

    def test_offline_record_with_omitted_network_validates(self) -> None:
        record = copy.deepcopy(OFFLINE_RECORD)
        del record["network"]
        VALIDATOR.validate(record)

    def test_live_missing_network_fails(self) -> None:
        record = copy.deepcopy(LIVE_RECORD)
        del record["network"]
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)

    def test_live_missing_endpoint_host_fails(self) -> None:
        record = copy.deepcopy(LIVE_RECORD)
        del record["endpointHost"]
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)

    def test_undeclared_property_rejected(self) -> None:
        record = copy.deepcopy(LIVE_RECORD)
        record["surprise"] = 1
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)

    def test_bad_sha_and_version_rejected(self) -> None:
        record = copy.deepcopy(LIVE_RECORD)
        record["fixtureSha256"] = "XYZ"
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)
        record = copy.deepcopy(LIVE_RECORD)
        record["verificationVersion"] = 2
        with self.assertRaises(Exception):
            VALIDATOR.validate(record)


if __name__ == "__main__":
    unittest.main()
