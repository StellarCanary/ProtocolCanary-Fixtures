"""Preserve the historical Protocol 29 structural records by network."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = REPO_ROOT / "protocol-29" / "evidence" / "history" / "verification"
LIVE_RECORDS = REPO_ROOT / "protocol-29" / "evidence" / "live"
CURRENT_FIXTURE = (
    REPO_ROOT / "protocol-29" / "rpc" / "p29-rpc-version-info-protocol-29.toml"
)
VERIFICATION_SCHEMA_PATH = REPO_ROOT / "schemas" / "verification-v1.schema.json"
JSONSCHEMA_LITE_PATH = REPO_ROOT / "tools" / "validate" / "jsonschema_lite.py"

STANDARD_NETWORK_PASSPHRASES = {
    "public": "Public Global Stellar Network ; September 2015",
    "testnet": "Test SDF Network ; September 2015",
    "futurenet": "Test SDF Future Network ; October 2022",
}


def _load_schema_validator():
    name = "canary_jsonschema_lite_p29_passphrase"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, JSONSCHEMA_LITE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _make_verification_record(
    *,
    network_name: str,
    passphrase: object,
    observed_protocol: int = 29,
) -> dict:
    return {
        "verificationVersion": 1,
        "fixtureId": "p29-rpc-version-info-protocol-29",
        "fixtureSha256": "a" * 64,
        "method": "live-read-only",
        "checkedAt": "2026-11-03T08:40:48Z",
        "verifier": {
            "name": "protocolcanary-fixtures-capture-live",
            "version": "1",
        },
        "outcome": "matched",
        "network": {
            "name": network_name,
            "passphrase": passphrase,
            "observedProtocol": observed_protocol,
        },
        "endpointHost": "localhost",
        "evidenceRef": "protocol-29/evidence/live/testnet/captures/get-version-info.json",
    }


class Protocol29HistoricalRecordTests(unittest.TestCase):
    def test_structural_records_remain_historical_and_network_specific(self) -> None:
        testnet = HISTORICAL / "testnet" / "p29-rpc-network-mismatch.json"
        futurenet = HISTORICAL / "futurenet" / "p29-rpc-network-mismatch.json"
        testnet_record = json.loads(testnet.read_text(encoding="utf-8"))
        futurenet_record = json.loads(futurenet.read_text(encoding="utf-8"))

        self.assertEqual(
            testnet_record["network"]["passphrase"],
            STANDARD_NETWORK_PASSPHRASES["testnet"],
        )
        self.assertEqual(
            futurenet_record["network"]["passphrase"],
            STANDARD_NETWORK_PASSPHRASES["futurenet"],
        )
        self.assertEqual(testnet_record["method"], "structural")
        self.assertEqual(futurenet_record["method"], "structural")
        self.assertNotIn("evidenceRef", testnet_record)
        self.assertNotIn("evidenceRef", futurenet_record)
        self.assertEqual(testnet_record["fixtureId"], "p29-rpc-network-mismatch")
        self.assertEqual(futurenet_record["fixtureId"], "p29-rpc-network-mismatch")
        current_sha = hashlib.sha256(CURRENT_FIXTURE.read_bytes()).hexdigest()
        self.assertNotEqual(testnet_record["fixtureSha256"], current_sha)
        self.assertNotEqual(futurenet_record["fixtureSha256"], current_sha)


class Protocol29PassphraseValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(VERIFICATION_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.network_schema = cls.schema["properties"]["network"]
        cls.validator = _load_schema_validator()

    def _validate_record(self, record: dict) -> list[str]:
        errors: list[str] = []
        for field in self.schema["required"]:
            if field not in record:
                errors.append(f"missing required field: {field}")
        if "network" in record:
            errors.extend(self.validator.validate(record["network"], self.network_schema))
        return errors

    def test_existing_p29_passphrase_records_validate_against_schema(self) -> None:
        record_paths = [
            HISTORICAL / "testnet" / "p29-rpc-network-mismatch.json",
            HISTORICAL / "futurenet" / "p29-rpc-network-mismatch.json",
            LIVE_RECORDS / "testnet" / "records" / "p29-rpc-version-info-protocol-29.live-read-only.json",
            LIVE_RECORDS / "futurenet" / "records" / "p29-rpc-version-info-protocol-29.live-read-only.json",
        ]
        for path in record_paths:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                record = json.loads(path.read_text(encoding="utf-8"))
                errors = self._validate_record(record)
                self.assertEqual(errors, [])
                passphrase = record["network"]["passphrase"]
                self.assertIsInstance(passphrase, str)
                self.assertGreaterEqual(len(passphrase), 1)
                self.assertEqual(passphrase.encode("utf-8").decode("utf-8"), passphrase)

    def test_standard_public_testnet_and_futurenet_passphrases_remain_unchanged(self) -> None:
        self.assertEqual(
            STANDARD_NETWORK_PASSPHRASES["public"],
            "Public Global Stellar Network ; September 2015",
        )
        self.assertEqual(
            STANDARD_NETWORK_PASSPHRASES["testnet"],
            "Test SDF Network ; September 2015",
        )
        self.assertEqual(
            STANDARD_NETWORK_PASSPHRASES["futurenet"],
            "Test SDF Future Network ; October 2022",
        )
        for network_name, passphrase in STANDARD_NETWORK_PASSPHRASES.items():
            with self.subTest(network=network_name):
                record = _make_verification_record(
                    network_name=network_name,
                    passphrase=passphrase,
                )
                self.assertEqual(self._validate_record(record), [])

    def test_custom_standalone_testnet_passphrases_validate_against_schema(self) -> None:
        standalone_passphrases = [
            "Standalone Network ; February 2017",
            "Local Custom Testnet ; 2026",
            "custom-local-testnet-p29",
        ]
        for passphrase in standalone_passphrases:
            with self.subTest(passphrase=passphrase):
                record = _make_verification_record(
                    network_name="standalone",
                    passphrase=passphrase,
                )
                serialized = json.dumps(record, ensure_ascii=False)
                round_tripped = json.loads(serialized)
                self.assertEqual(round_tripped["network"]["passphrase"], passphrase)
                self.assertEqual(self._validate_record(round_tripped), [])

    def test_passphrase_length_type_and_network_object_schema_rules(self) -> None:
        empty_passphrase = _make_verification_record(
            network_name="standalone",
            passphrase="",
        )
        self.assertNotEqual(self._validate_record(empty_passphrase), [])

        non_string_passphrase = _make_verification_record(
            network_name="standalone",
            passphrase=12345,
        )
        self.assertNotEqual(self._validate_record(non_string_passphrase), [])

        missing_passphrase = _make_verification_record(
            network_name="standalone",
            passphrase="Standalone Network ; February 2017",
        )
        del missing_passphrase["network"]["passphrase"]
        self.assertNotEqual(self._validate_record(missing_passphrase), [])

        extra_network_field = _make_verification_record(
            network_name="standalone",
            passphrase="Standalone Network ; February 2017",
        )
        extra_network_field["network"]["extra"] = "unexpected"
        self.assertNotEqual(self._validate_record(extra_network_field), [])


if __name__ == "__main__":
    unittest.main()
