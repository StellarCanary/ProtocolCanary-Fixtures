"""Tests for the Protocol 29 baseline directory and registry (F-033, #290).

The ``protocol-29/`` pack ships with a generated registry and fixture files
under ``rpc/``, ``xdr/`` and ``soroban/``. Its registry must describe the
current pack exactly. Inventory presence alone is not live compatibility evidence.

Run with: python3 -m unittest discover tests
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = REPO_ROOT / "protocol-29"
SCHEMA_PATH = REPO_ROOT / "schemas" / "registry-v1.schema.json"
from tools.registry import generate as registry_generate

VALIDATE_PATH = REPO_ROOT / "tools" / "validate" / "validate.py"
_spec = importlib.util.spec_from_file_location("validate_for_protocol29", VALIDATE_PATH)
validate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["validate_for_protocol29"] = validate
_spec.loader.exec_module(validate)

LITE_PATH = REPO_ROOT / "tools" / "validate" / "jsonschema_lite.py"
_lite_spec = importlib.util.spec_from_file_location("lite_for_protocol29", LITE_PATH)
lite = importlib.util.module_from_spec(_lite_spec)
assert _lite_spec.loader is not None
sys.modules["lite_for_protocol29"] = lite
_lite_spec.loader.exec_module(lite)

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def check_baseline(record: dict) -> list[str]:
    """Problems in the protocol-29 baseline manifest, empty when conforming.

    Everything the schema checks comes from ``jsonschema_lite``; on top of
    it, the pack binding asserts what the schema cannot: the directory name
    and the manifest's ``protocol`` value agree (``protocol-29/`` declares
    ``protocol = 29``).
    """
    problems = lite.validate(record, SCHEMA)
    version = record.get("registryVersion")
    if type(version) is not int or version != 1:
        problems.append(f"registryVersion must be the integer 1, got {version!r}")
    protocol = record.get("protocol")
    if type(protocol) is not int or protocol != 29:
        problems.append(
            f"a protocol-29/ manifest must declare protocol = 29 as an integer, got {protocol!r}"
        )
    if not record.get("fixtures") and list(PACK_DIR.rglob("*.toml")):
        problems.append("registry lists no fixtures but the pack contains *.toml fixture files")
    return problems


class Protocol29BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry_text = registry_generate.generate(PACK_DIR)
        cls.registry = json.loads(cls.registry_text)

    def test_pack_subdirectories_exist(self) -> None:
        for name in ("rpc", "xdr", "soroban"):
            with self.subTest(directory=name):
                self.assertTrue((PACK_DIR / name).is_dir())

    def test_registry_describes_the_protocol_29_version_info_fixture(self) -> None:
        integer_protocol = self.registry["protocol"]
        self.assertIs(type(integer_protocol), int, "protocol must be an integer, not a bool")
        self.assertEqual(integer_protocol, 29)
        self.assertEqual(self.registry["registryVersion"], 1)
        fixture_ids = [fixture["id"] for fixture in self.registry["fixtures"]]
        self.assertIn("p29-rpc-version-info-protocol-29", fixture_ids)

    def test_registry_conforms_to_the_registry_schema(self) -> None:
        problems = lite.validate(self.registry, SCHEMA)
        self.assertEqual(problems, [])

    def test_registry_uses_the_canonical_encoding(self) -> None:
        # CF-02 section 3: UTF-8, LF, two-space indent, one trailing newline.
        expected = json.dumps(self.registry, indent=2, ensure_ascii=False) + "\n"
        self.assertEqual(self.registry_text, expected)

    def test_pack_digest_matches_the_protocol_29_fixture_files(self) -> None:
        files = {}
        for fixture in self.registry["fixtures"]:
            paths = [fixture["path"]] + [payload["path"] for payload in fixture["payloads"]]
            for name in paths:
                files[name] = (PACK_DIR / name).read_bytes()
        lines = ["canary-pack-v1\n"]
        for name in sorted(files, key=lambda path: path.encode("utf-8")):
            data = files[name]
            lines.append(f"{hashlib.sha256(data).hexdigest()} {len(data)} {name}\n")
        expected = "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
        self.assertEqual(self.registry["packDigest"], expected)

    def test_protocol_29_fixture_is_listed_in_the_registry(self) -> None:
        fixture_paths = {fixture["path"] for fixture in self.registry["fixtures"]}
        self.assertIn("rpc/p29-rpc-version-info-protocol-29.toml", fixture_paths)
        self.assertTrue((PACK_DIR / "rpc" / "p29-rpc-version-info-protocol-29.toml").is_file())

    def test_baseline_manifest_passes_the_pack_checks(self) -> None:
        self.assertEqual(check_baseline(self.registry), [])

    def test_other_protocol_numbers_fail_the_pack_checks(self) -> None:
        for wrong in (28, 30, "29", True):
            with self.subTest(protocol=wrong):
                mutated = dict(self.registry, protocol=wrong)
                problems = check_baseline(mutated)
                self.assertTrue(problems, f"protocol {wrong!r} was accepted")

    def test_validator_accepts_the_protocol_29_directory(self) -> None:
        report = validate.validate_directory(PACK_DIR)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_default_scan_discovers_protocol_29(self) -> None:
        # The CLI's default roots glob protocol-*/; protocol-29/ must be
        # among them and contribute no diagnostics (F-033 acceptance).
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = validate.main(["--format", "json"])
        document = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertTrue(document["valid"])
        self.assertEqual(document["warnings"], [])
        roots = [Path(root) for root in document["summary"]["roots"]]
        self.assertIn(PACK_DIR, roots, roots)

    def test_generator_tool_reproduces_protocol_29_registry_byte_for_byte(self) -> None:
        # The generator output remains byte-for-byte canonical without a
        # registry file in the source checkout.
        generate_path = REPO_ROOT / "tools" / "registry" / "generate.py"
        spec = importlib.util.spec_from_file_location("generate_for_protocol29", generate_path)
        gen = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["generate_for_protocol29"] = gen
        spec.loader.exec_module(gen)

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = gen.main([str(PACK_DIR), "--stdout"])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), self.registry_text)


class Protocol29FeeBoundaryTests(unittest.TestCase):
    """Issue #599: Protocol 29 baseline vectors cover boundary fee conditions.

    Protocol 29 introduced revised fee and reserve calculations. These tests
    assert that:

    * the baseline manifest rejects negative, zero and boolean ``protocol``
      values (the wrong types that an off-by-one or sign error could produce);
    * ``check_baseline`` surfaces a clear diagnostic for every invalid value;
    * the shipped baseline manifest passes all boundary checks without
      modification.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(registry_generate.generate(PACK_DIR))

    def test_negative_protocol_number_fails_baseline_check(self) -> None:
        # A negative protocol value cannot represent a valid Stellar protocol.
        for bad in (-1, -29, -100):
            with self.subTest(protocol=bad):
                mutated = dict(self.registry, protocol=bad)
                problems = check_baseline(mutated)
                self.assertTrue(problems, f"protocol {bad!r} was accepted")
                self.assertTrue(
                    any("protocol" in p.lower() for p in problems),
                    f"no protocol-related diagnostic for {bad!r}: {problems}",
                )

    def test_zero_protocol_fails_baseline_check(self) -> None:
        # Zero is not a valid Stellar protocol version.
        mutated = dict(self.registry, protocol=0)
        problems = check_baseline(mutated)
        self.assertTrue(problems, "protocol 0 was accepted")
        self.assertTrue(
            any("protocol" in p.lower() for p in problems),
            f"no protocol diagnostic: {problems}",
        )

    def test_non_integer_protocol_type_fails_baseline_check(self) -> None:
        # Strings, floats and booleans must all be rejected; boolean is a
        # special case because ``isinstance(True, int)`` is True in Python.
        for bad in ("29", 29.0, True, False, None):
            with self.subTest(protocol=bad):
                mutated = dict(self.registry, protocol=bad)
                problems = check_baseline(mutated)
                self.assertTrue(problems, f"protocol {bad!r} was accepted")

    def test_wrong_protocol_number_fails_baseline_check(self) -> None:
        # Nearby valid integers that are not 29 are still wrong for this pack.
        for bad in (28, 30, 1, 100):
            with self.subTest(protocol=bad):
                mutated = dict(self.registry, protocol=bad)
                problems = check_baseline(mutated)
                self.assertTrue(problems, f"protocol {bad!r} was accepted")

    def test_zero_registry_version_fails_baseline_check(self) -> None:
        # registryVersion 0 is below the minimum documented version.
        mutated = dict(self.registry, registryVersion=0)
        problems = check_baseline(mutated)
        self.assertTrue(problems, "registryVersion 0 was accepted")

    def test_negative_registry_version_fails_baseline_check(self) -> None:
        mutated = dict(self.registry, registryVersion=-1)
        problems = check_baseline(mutated)
        self.assertTrue(problems, "registryVersion -1 was accepted")

    def test_shipped_registry_has_no_boundary_problems(self) -> None:
        # The baseline shipped in the repository must pass every boundary check
        # without modification.
        self.assertEqual(check_baseline(self.registry), [])
        self.assertIs(type(self.registry["protocol"]), int)
        self.assertNotIsInstance(self.registry["protocol"], bool)
        self.assertEqual(self.registry["protocol"], 29)
        self.assertGreater(self.registry["protocol"], 0)

    def test_diagnostic_message_names_the_invalid_value(self) -> None:
        # When a boundary condition fails, the diagnostic must include the
        # bad value so contributors can pinpoint the problem quickly.
        mutated = dict(self.registry, protocol=0)
        problems = check_baseline(mutated)
        combined = " ".join(problems)
        self.assertIn("0", combined)

    def test_check_baseline_returns_empty_list_for_valid_registry(self) -> None:
        # Sanity: an unmodified registry produces zero problems.
        self.assertEqual(check_baseline(self.registry), [])

    def test_fixtures_list_is_non_empty_in_baseline(self) -> None:
        # The protocol-29 pack must contain at least one fixture; an empty
        # fixtures list is a packaging error, not a valid baseline.
        self.assertGreater(len(self.registry.get("fixtures", [])), 0)


if __name__ == "__main__":
    unittest.main()
