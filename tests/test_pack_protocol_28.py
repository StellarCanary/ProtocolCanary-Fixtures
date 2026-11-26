"""Pack-level checks for the Protocol 28 fixture pack.

These are structural/offline checks (no network, no execution) that this
specific release's pack matches its own documented inventory. The actual
end-to-end verification that these fixtures pass when run by
Protocol-Canary against live testnet is recorded in each fixture's header
comment and in docs/protocol-28.md, not re-run here — see CONTRIBUTING.md
on why CI does not require a live RPC endpoint.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
VALIDATE_PATH = REPO_ROOT / "tools" / "validate" / "validate.py"

_spec = importlib.util.spec_from_file_location("validate", VALIDATE_PATH)
validate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["validate"] = validate
_spec.loader.exec_module(validate)

from tools.pack import pack
from tools.registry import generate as registry_generate
from tools.validate import jsonschema_lite

PACK = REPO_ROOT / "protocol-28"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
FIXTURE_SCHEMA_PATH = REPO_ROOT / "schemas" / "fixture-v1.schema.json"
FEE_STATS_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "rpc" / "get-fee-stats.toml"
FEE_STATS_VECTOR_PATH = REPO_ROOT / "tests" / "vectors" / "rpc" / "get-fee-stats.json"

FEE_PERCENTILE_KEYS = (
    "min",
    "p10",
    "p20",
    "p30",
    "p40",
    "p50",
    "p60",
    "p70",
    "p80",
    "p90",
    "p95",
    "p99",
    "max",
)

# Test-local JSON Schema mirroring Stellar RPC's documented `getFeeStats`
# response structure; `schemas/fee-stats.schema.json` is not shipped in `schemas/`.
_FEE_DISTRIBUTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "max",
        "min",
        "mode",
        "p10",
        "p20",
        "p30",
        "p40",
        "p50",
        "p60",
        "p70",
        "p80",
        "p90",
        "p95",
        "p99",
        "transactionCount",
        "ledgerCount",
    ],
    "properties": {
        **{
            key: {"type": "string", "pattern": "^(0|[1-9][0-9]*)$"}
            for key in (
                "max",
                "min",
                "mode",
                "p10",
                "p20",
                "p30",
                "p40",
                "p50",
                "p60",
                "p70",
                "p80",
                "p90",
                "p95",
                "p99",
                "transactionCount",
            )
        },
        "ledgerCount": {"type": "integer", "minimum": 0},
    },
}

FEE_STATS_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sorobanInclusionFee", "inclusionFee", "latestLedger"],
    "properties": {
        "sorobanInclusionFee": _FEE_DISTRIBUTION_SCHEMA,
        "inclusionFee": _FEE_DISTRIBUTION_SCHEMA,
        "latestLedger": {"type": "integer", "minimum": 1},
    },
}


def check_fee_percentiles_monotonic(distribution: dict) -> list[str]:
    """Return errors if fee percentile brackets are not monotonically non-decreasing."""
    errors: list[str] = []
    previous_key = FEE_PERCENTILE_KEYS[0]
    previous_value = int(distribution[previous_key])
    for key in FEE_PERCENTILE_KEYS[1:]:
        current_value = int(distribution[key])
        if current_value < previous_value:
            errors.append(
                f"{key} ({current_value}) is less than {previous_key} ({previous_value})"
            )
        previous_key = key
        previous_value = current_value
    return errors

EXPECTED_IDS_BY_SURFACE = {
    "xdr": {
        "p28-xdr-cap83-empty-tx-set",
        "p28-xdr-cap83-empty-tx-set-malformed",
        "p28-xdr-cap85-external-ref-roundtrip",
        "p28-xdr-cap85-external-ref-malformed",
        "p28-xdr-contract-executable-wasm-roundtrip",
        "p28-xdr-contract-executable-wasm-decode-success",
        "p28-xdr-contract-executable-wasm-decode-failure",
        "p28-xdr-contract-executable-stellar-asset-roundtrip",
        "p28-xdr-contract-executable-stellar-asset-decode-success",
        "p28-xdr-contract-executable-stellar-asset-decode-failure",
        "p28-xdr-stellar-value-basic-roundtrip",
        "p28-xdr-stellar-value-basic-decode-success",
        "p28-xdr-stellar-value-basic-decode-failure",
        "p28-xdr-stellar-value-signed-roundtrip",
        "p28-xdr-stellar-value-signed-decode-success",
        "p28-xdr-stellar-value-signed-decode-failure",
        "p28-xdr-stellar-value-boundary-truncated",
        "p28-xdr-stellar-value-boundary-trailing-bytes",
        "p28-xdr-stellar-value-boundary-unknown-ext-discriminant",
        "p28-xdr-transaction-envelope-v0-roundtrip",
        "p28-xdr-transaction-envelope-v0-decode-failure",
        "p28-xdr-transaction-envelope-v1-roundtrip",
        "p28-xdr-transaction-envelope-v1-decode-failure",
        "p28-xdr-transaction-envelope-soroban-invoke-roundtrip",
        "p28-xdr-transaction-envelope-soroban-invoke-decode-failure",
        "p28-xdr-transaction-envelope-fee-bump-roundtrip",
        "p28-xdr-transaction-envelope-fee-bump-decode-failure",
        "p28-xdr-ledger-entry-account",
        "p28-xdr-ledger-entry-account-truncated",
        "p28-xdr-ledger-entry-contract-code",
        "p28-xdr-ledger-entry-contract-code-truncated",
        "p28-xdr-ledger-entry-contract-data",
        "p28-xdr-ledger-entry-contract-data-key-truncated",
        "p28-xdr-ledger-entry-trustline",
        "p28-xdr-ledger-entry-trustline-truncated",
        "p28-xdr-ledger-entry-trustline-unknown-asset-type",
        "p28-xdr-ledger-entry-ttl",
        "p28-xdr-ledger-entry-ttl-missing-live-until",
        "p28-xdr-scval-address-account",
        "p28-xdr-scval-address-contract",
        "p28-xdr-scval-address-unknown-discriminant",
        "p28-xdr-scval-map-empty",
        "p28-xdr-scval-map-multi",
        "p28-xdr-scval-map-nested",
        "p28-xdr-scval-map-one",
        "p28-xdr-scval-map-truncated-after-key",
        "p28-xdr-scval-map-unsorted-keys",
        "p28-xdr-scval-vec-count-exceeds-data",
        "p28-xdr-scval-vec-empty",
        "p28-xdr-scval-vec-multi",
        "p28-xdr-scval-vec-null",
        "p28-xdr-scval-vec-one",
        "p28-xdr-scval-bool-false",
        "p28-xdr-scval-bool-true",
        "p28-xdr-scval-bytes-empty",
        "p28-xdr-scval-bytes-small",
        "p28-xdr-scval-bytes-truncated",
        "p28-xdr-scval-duration",
        "p28-xdr-scval-i128-max",
        "p28-xdr-scval-i128-min",
        "p28-xdr-scval-i128-truncated",
        "p28-xdr-scval-i128-zero",
        "p28-xdr-scval-i256-max",
        "p28-xdr-scval-i256-min",
        "p28-xdr-scval-i256-zero",
        "p28-xdr-scval-i32-min",
        "p28-xdr-scval-i64-min",
        "p28-xdr-scval-string-empty",
        "p28-xdr-scval-string-small",
        "p28-xdr-scval-string-truncated",
        "p28-xdr-scval-symbol-32-boundary",
        "p28-xdr-scval-symbol-33-invalid",
        "p28-xdr-scval-symbol-empty",
        "p28-xdr-scval-symbol-small",
        "p28-xdr-scval-timepoint",
        "p28-xdr-scval-u128-high-bit",
        "p28-xdr-scval-u128-max",
        "p28-xdr-scval-u128-zero",
        "p28-xdr-scval-u256-max",
        "p28-xdr-scval-u256-truncated",
        "p28-xdr-scval-u256-zero",
        "p28-xdr-scval-u32-max",
        "p28-xdr-scval-u32-truncated",
        "p28-xdr-scval-u64-max",
        "p28-xdr-scval-u64-truncated",
        "p28-xdr-scval-void",
    },
    "rpc": {"p28-rpc-network", "p28-rpc-latest-ledger"},
    "soroban": {
        "p28-soroban-native-asset-name",
        "p28-soroban-sim-error-unknown-function",
        "p28-soroban-sim-error-missing-contract",
        "p28-soroban-sim-error-arg-count",
        "p28-soroban-sim-error-arg-type",
    },
}


class Protocol28PackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = validate.validate_directory(PACK)
        fixtures = [
            validate.load_fixture(p, validate.Report()) for p in validate.find_fixture_files(PACK)
        ]
        self.fixtures = [fx for fx in fixtures if fx is not None]

    def test_pack_is_structurally_valid(self) -> None:
        self.assertEqual(self.report.errors, [])

    def test_every_fixture_targets_protocol_28(self) -> None:
        for fx in self.fixtures:
            self.assertEqual(fx.data.get("protocol"), 28, fx.path)

    def test_fixture_paths_match_declared_surface(self) -> None:
        for fx in self.fixtures:
            relative_path = fx.path.relative_to(PACK)
            self.assertEqual(relative_path.parts[0], fx.data.get("surface"), fx.path)

    def test_fixture_ids_follow_the_p_protocol_surface_convention(self) -> None:
        # CONTRIBUTING.md documents `p<protocol>-<surface>-<slug>` for fixture
        # IDs, and the schema's pattern only requires lowercase/non-empty. This
        # per-pack check enforces the documented prefix for protocol-28.
        for fx in self.fixtures:
            expected_prefix = f"p{fx.data.get('protocol')}-{fx.data.get('surface')}-"
            self.assertTrue(
                str(fx.data.get("id", "")).startswith(expected_prefix),
                f"{fx.path}: id {fx.data.get('id')!r} does not start with {expected_prefix!r}",
            )

    def test_every_fixture_has_a_source_reference(self) -> None:
        for fx in self.fixtures:
            self.assertTrue(fx.data.get("source_reference"), fx.path)

    def test_every_fixture_starts_with_a_header_comment(self) -> None:
        for path in validate.find_fixture_files(PACK):
            first_non_empty = next(
                (line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()),
                "",
            )
            self.assertTrue(first_non_empty.lstrip().startswith("#"), path)

    def test_expected_fixture_ids_are_present_per_surface(self) -> None:
        by_surface: dict[str, set[str]] = {"xdr": set(), "rpc": set(), "soroban": set()}
        for fx in self.fixtures:
            surface = fx.data.get("surface")
            if surface in by_surface:
                by_surface[surface].add(fx.data.get("id"))
        for surface, required_ids in EXPECTED_IDS_BY_SURFACE.items():
            with self.subTest(surface=surface):
                self.assertTrue(
                    required_ids <= by_surface.get(surface, set()),
                    f"required baseline fixtures are missing for {surface}",
                )

    def test_changelog_fixture_ids_still_exist_or_are_marked_removed(self) -> None:
        changelog = CHANGELOG.read_text(encoding="utf-8")
        unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0]
        actual_ids = {str(fx.data.get("id")) for fx in self.fixtures}

        for line in unreleased.splitlines():
            for fixture_id in re.findall(r"`(p\d+-[a-z0-9-]+)`", line):
                if fixture_id not in actual_ids:
                    status = line.lower()
                    self.assertTrue(
                        "removed" in status or "deprecated" in status,
                        f"CHANGELOG.md references missing fixture id {fixture_id!r}",
                    )

    def test_no_fixture_claims_cap_0086(self) -> None:
        # CAP-0086 is a documented gap (see docs/protocol-28.md); a fixture
        # claiming to cover it would be fabricated coverage.
        for fx in self.fixtures:
            self.assertNotIn("cap-0086", fx.data.get("category", "").lower(), fx.path)
            self.assertNotIn("CAP-0086", fx.data.get("source_reference", ""), fx.path)

    def test_protocol_27_pack_has_no_fixtures_yet(self) -> None:
        p27 = REPO_ROOT / "protocol-27"
        self.assertEqual(validate.find_fixture_files(p27), [])
        readme = p27 / "README.md"
        self.assertTrue(
            readme.is_file() and "intentionally empty" in readme.read_text(encoding="utf-8").lower(),
            "protocol-27/README.md must state the pack is intentionally empty",
        )

        # protocol-27/README.md documents the pack as intentionally empty as a
        # matter of policy (no placeholder fixtures). The *.toml-only check
        # above cannot see stray non-fixture content — an accidentally
        # committed scratch file, a draft fixture saved with the wrong
        # extension, or a leftover subdirectory — so assert the documented
        # invariant directly: the pack's only file is README.md and every
        # directory inside it is empty.
        self.assertEqual(
            sorted(p.relative_to(p27).as_posix() for p in p27.rglob("*") if p.is_file()),
            ["README.md"],
        )
        non_empty_dirs = [p for p in p27.rglob("*") if p.is_dir() and any(p.iterdir())]
        self.assertEqual(non_empty_dirs, [])


    def test_no_fixture_files_outside_allowed_subdirectories(self) -> None:
        allowed_dirs = {"xdr", "rpc", "soroban"}
        for toml_path in PACK.rglob("*.toml"):
            relative_path = toml_path.relative_to(PACK)
            self.assertIn(
                relative_path.parts[0],
                allowed_dirs,
                f"Fixture file {relative_path} is located outside allowed subdirectories ({allowed_dirs})",
            )


class Protocol28FeeStatsTests(unittest.TestCase):
    """Fee-stats fixture, schema, percentile monotonicity, and manifest tests (#608).

    Note: ``schemas/fee-stats.schema.json`` does not exist in ``schemas/`` and
    ``protocol-28/`` ships ``p28-rpc-network`` and ``p28-rpc-latest-ledger``
    rather than a live ``get-fee-stats`` fixture. These tests verify the
    repository's Protocol 28 ``tests/fixtures/rpc/get-fee-stats.toml`` fixture,
    the captured ``tests/vectors/rpc/get-fee-stats.json`` vector against a
    test-local JSON Schema via ``jsonschema_lite``, percentile monotonicity
    (including p10 <= p50 <= p90 <= p99), and archive manifest inclusion.
    """

    def test_fee_stats_fixture_conforms_to_protocol_28_and_fixture_schema(self) -> None:
        fixture_data = tomllib.loads(FEE_STATS_FIXTURE_PATH.read_text(encoding="utf-8"))
        fixture_schema = json.loads(FIXTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
        rpc_method_schema = fixture_schema["allOf"][1]["then"]["properties"]["method"]
        self.assertEqual(jsonschema_lite.validate(fixture_data["method"], rpc_method_schema), [])

        with tempfile.TemporaryDirectory() as tmp:
            fixture_copy = Path(tmp) / "get-fee-stats.toml"
            shutil.copy2(FEE_STATS_FIXTURE_PATH, fixture_copy)
            report = validate.validate_directory(Path(tmp))
        self.assertEqual(report.errors, [])
        self.assertEqual(fixture_data["protocol"], 28)
        self.assertEqual(fixture_data["surface"], "rpc")
        self.assertEqual(fixture_data["method"], "get-fee-stats")
        fields = {entry["field"] for entry in fixture_data["assert"]}
        self.assertEqual(fields, {"sorobanInclusionFee", "inclusionFee", "latestLedger"})

    def test_fee_stats_vector_conforms_to_schema_and_monotonic_percentiles(self) -> None:
        capture = json.loads(FEE_STATS_VECTOR_PATH.read_text(encoding="utf-8"))
        result = capture["response"]["result"]
        self.assertEqual(jsonschema_lite.validate(result, FEE_STATS_RESULT_SCHEMA), [])

        for key in ("sorobanInclusionFee", "inclusionFee"):
            with self.subTest(distribution=key):
                dist = result[key]
                self.assertEqual(check_fee_percentiles_monotonic(dist), [])
                p10, p50, p90, p99 = (int(dist[p]) for p in ("p10", "p50", "p90", "p99"))
                self.assertLessEqual(p10, p50)
                self.assertLessEqual(p50, p90)
                self.assertLessEqual(p90, p99)

        broken_result = json.loads(json.dumps(result))
        del broken_result["inclusionFee"]
        self.assertTrue(jsonschema_lite.validate(broken_result, FEE_STATS_RESULT_SCHEMA))

        non_monotonic = dict(result["sorobanInclusionFee"], p50="500", p90="100")
        errors = check_fee_percentiles_monotonic(non_monotonic)
        self.assertTrue(any("p60" in err or "p90" in err for err in errors), errors)

    def test_protocol_28_archive_manifest_references_fixtures_and_fee_stats(self) -> None:
        registry = json.loads(registry_generate.generate(PACK))
        members, digest, protocol = pack.collect_members(PACK)
        self.assertEqual(protocol, 28)
        self.assertEqual(digest, registry["packDigest"])
        archive_registry = json.loads(members["registry.json"].decode("utf-8"))
        self.assertEqual(archive_registry, registry)
        listed_paths = {entry["path"] for entry in archive_registry["fixtures"]}
        self.assertIn("rpc/p28-rpc-network.toml", listed_paths)
        self.assertIn("rpc/p28-rpc-latest-ledger.toml", listed_paths)

        with tempfile.TemporaryDirectory() as tmp:
            temp_pack = Path(tmp) / "protocol-28"
            shutil.copytree(PACK, temp_pack)
            fee_dest = temp_pack / "rpc" / "get-fee-stats.toml"
            shutil.copy2(FEE_STATS_FIXTURE_PATH, fee_dest)
            expected_sha = hashlib.sha256(fee_dest.read_bytes()).hexdigest()

            temp_members, _, temp_protocol = pack.collect_members(temp_pack)
            self.assertEqual(temp_protocol, 28)
            manifest = json.loads(temp_members["registry.json"].decode("utf-8"))
            by_id = {entry["id"]: entry for entry in manifest["fixtures"]}
            self.assertIn("test-rpc-fee-stats", by_id)
            self.assertEqual(by_id["test-rpc-fee-stats"]["path"], "rpc/get-fee-stats.toml")
            self.assertEqual(by_id["test-rpc-fee-stats"]["sha256"], expected_sha)


if __name__ == "__main__":
    unittest.main()

