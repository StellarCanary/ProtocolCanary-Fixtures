"""Pack-level checks for the intentionally-empty Protocol 27 fixture pack.

Protocol 27 ("Zipper", CAP-0071-01 and CAP-0071-02) is not yet verified in
this repository. This test asserts the documented gap: the directory contains
no fixtures, no fixture claims CAP-0071-01/02 category/source, and the
documentation files describe the gap rather than fabricating coverage.

Issue #607 also asks for Protocol 27 pack manifest schema and capability tag
validation. Note that ``schemas/pack-manifest.schema.json`` and deprecated
legacy capability tags do not exist in this repository: the repository's actual
schemas are ``schemas/registry-v1.schema.json`` and
``schemas/fixture-v1.schema.json``, and ``tests/fixtures/capabilities.json``
publishes the five canonical ``required_capabilities`` values. The tests below
verify Protocol 27 pack structure, empty baseline manifest generation/schema
rules, and capability tag validation against those actual contracts.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.pack import pack
from tools.registry import generate as registry_generate
from tools.validate import jsonschema_lite, validate

PACK = REPO_ROOT / "protocol-27"
README = PACK / "README.md"
DOCS = REPO_ROOT / "docs" / "protocol-27.md"
REGISTRY_SCHEMA_PATH = REPO_ROOT / "schemas" / "registry-v1.schema.json"
FIXTURE_SCHEMA_PATH = REPO_ROOT / "schemas" / "fixture-v1.schema.json"
CAPABILITIES_PATH = REPO_ROOT / "tests" / "fixtures" / "capabilities.json"


class Protocol27PackTests(unittest.TestCase):
    def test_protocol_27_pack_has_no_fixtures_yet(self) -> None:
        self.assertEqual(validate.find_fixture_files(PACK), [])

    def test_protocol_27_readme_explains_the_gap(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("intentionally empty", text.lower())
        self.assertIn("CAP-0071-01", text)
        self.assertIn("CAP-0071-02", text)
        for ref in (
            "stellar/stellar-protocol/blob/master/core/cap-0071-01.md",
            "stellar/stellar-protocol/blob/master/core/cap-0071-02.md",
        ):
            self.assertIn(ref, text)
        self.assertIn(
            "stellar.org/blog/foundation-news/stellar-zipper-protocol-27-upgrade-guide",
            text,
        )

    def test_protocol_27_docs_describe_the_gap(self) -> None:
        text = DOCS.read_text(encoding="utf-8")
        self.assertIn("CAP-0071-01", text)
        self.assertIn("CAP-0071-02", text)
        self.assertTrue(
            "nothing, yet" in text.lower() or "no fixture" in text.lower(),
            "docs/protocol-27.md should explicitly state the pack has no fixture yet",
        )
        for cap in ("cap-0071-01.md", "cap-0071-02.md"):
            self.assertIn(cap, text)
        self.assertIn(
            "stellar.org/blog/foundation-news/stellar-zipper-protocol-27-upgrade-guide",
            text,
        )

    def test_no_fixture_claims_cap_0071_in_protocol_27(self) -> None:
        # Even if a fixture were accidentally added later, this asserts the
        # documented gap is not violated by claiming CAP-0071 coverage.
        files = validate.find_fixture_files(PACK)
        self.assertEqual(files, [])

    def test_protocol_27_structure_has_only_readme_and_passes_validator(self) -> None:
        files = sorted(p.relative_to(PACK).as_posix() for p in PACK.rglob("*") if p.is_file())
        self.assertEqual(files, ["README.md"])
        non_empty_dirs = [p for p in PACK.rglob("*") if p.is_dir() and any(p.iterdir())]
        self.assertEqual(non_empty_dirs, [])

        report = validate.validate_directory(PACK)
        self.assertEqual(report.errors, [])

    def test_protocol_27_empty_manifest_generation_and_archive_rules(self) -> None:
        manifest_text = registry_generate.generate(PACK, allow_empty=True, protocol=27)
        manifest = json.loads(manifest_text)
        expected_empty_digest = "sha256:" + hashlib.sha256(b"canary-pack-v1\n").hexdigest()

        self.assertEqual(manifest["registryVersion"], 1)
        self.assertEqual(manifest["protocol"], 27)
        self.assertEqual(manifest["fixtures"], [])
        self.assertEqual(manifest["packDigest"], expected_empty_digest)

        registry_schema = json.loads(REGISTRY_SCHEMA_PATH.read_text(encoding="utf-8"))
        problems = jsonschema_lite.validate(manifest, registry_schema)
        self.assertEqual(len(problems), 1)
        self.assertIn("fewer than 1", problems[0])

        with self.assertRaisesRegex(registry_generate.PackError, r"no \*\.toml fixture files"):
            registry_generate.generate(PACK)

        with self.assertRaisesRegex(pack.PackError, r"no \*\.toml fixture files"):
            pack.collect_members(PACK)

    def test_capability_tags_under_fixture_and_registry_schemas(self) -> None:
        fixture_schema = json.loads(FIXTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
        registry_schema = json.loads(REGISTRY_SCHEMA_PATH.read_text(encoding="utf-8"))
        canonical_caps = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))[
            "required_capabilities"
        ]
        self.assertEqual(set(canonical_caps), set(validate.CAPABILITIES))

        cap_prop_schema = fixture_schema["properties"]["required_capabilities"]
        self.assertEqual(jsonschema_lite.validate(canonical_caps, cap_prop_schema), [])

        legacy_caps = ["legacy-soroban-v1"]
        self.assertTrue(jsonschema_lite.validate(legacy_caps, cap_prop_schema))

        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "legacy-cap.toml"
            fixture_path.write_text(
                'id = "p27-xdr-legacy-cap"\n'
                "protocol = 27\n"
                'surface = "xdr"\n'
                'category = "cap-0071-01"\n'
                'description = "synthetic unapproved capability check"\n'
                'source_reference = "CAP-0071"\n'
                'required_capabilities = ["legacy-soroban-v1"]\n'
                'type = "StellarValue"\n'
                'kind = "decode-success"\n'
                'value_base64 = "AAAAAA=="\n',
                encoding="utf-8",
            )
            report = validate.validate_directory(Path(tmp))
            self.assertTrue(
                any("unknown capability 'legacy-soroban-v1'" in str(err) for err in report.errors),
                report.errors,
            )

        registry_doc = {
            "registryVersion": 1,
            "protocol": 27,
            "fixtures": [
                {
                    "id": "p27-xdr-legacy-cap",
                    "path": "xdr/legacy-cap.toml",
                    "sha256": "a" * 64,
                    "surface": "xdr",
                    "category": "cap-0071-01",
                    "description": "registry entry carrying requiredCapabilities",
                    "payloads": [],
                    "requiredCapabilities": canonical_caps,
                }
            ],
            "packDigest": "sha256:" + ("0" * 64),
        }
        self.assertEqual(jsonschema_lite.validate(registry_doc, registry_schema), [])


if __name__ == "__main__":
    unittest.main()
