"""Edge-case unit tests for tools/inventory/compare.py (issue #672).

Note: ``tools/inventory/compare.py`` compares two pre-generated JSON documents
(an engine inventory from ``stellar-canary fixtures --format json`` and a pack
``registry-v1.json``) rather than scanning TOML fixture directories directly.
An absent protocol directory on the engine side is represented by
``"directoryFound": false``. These tests cover diff computation, empty
baselines, malformed/corrupted JSON or UTF-8 inputs, missing metadata fields,
contradictory counts, duplicate IDs, and protocol mismatches without crashing.

Run with: python3 -m unittest tests/test_inventory_compare_edges.py
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.inventory import compare

SHA_A = "a" * 64
DIGEST_A = "sha256:" + "1" * 64


def make_engine_fixture(
    identifier: str,
    surface: str = "xdr",
    category: str = "cap-0083",
    path: str | None = None,
) -> dict:
    """Build a minimal valid engine inventory fixture entry."""
    return {
        "id": identifier,
        "protocol": 28,
        "surface": surface,
        "category": category,
        "description": f"fixture {identifier}",
        "path": path or f"{surface}/{identifier}.toml",
        "requiredCapabilities": [],
    }


def make_registry_fixture(
    identifier: str,
    surface: str = "xdr",
    category: str = "cap-0083",
    path: str | None = None,
) -> dict:
    """Build a minimal valid registry fixture entry."""
    return {
        "id": identifier,
        "path": path or f"{surface}/{identifier}.toml",
        "sha256": SHA_A,
        "surface": surface,
        "category": category,
        "description": f"fixture {identifier}",
        "payloads": [],
    }


def make_inventory(
    fixtures: list[dict],
    *,
    protocol: int = 28,
    version: int = 1,
    fixture_format: int = 1,
    total: int | None = None,
    directory_found: bool = True,
) -> dict:
    """Build a minimal valid engine inventory document."""
    return {
        "inventoryVersion": version,
        "toolVersion": "0.2.0",
        "fixtureFormat": fixture_format,
        "protocol": protocol,
        "directoryFound": directory_found,
        "counts": {
            "total": len(fixtures) if total is None else total,
            "xdr": len([f for f in fixtures if f.get("surface") == "xdr"]),
            "rpc": len([f for f in fixtures if f.get("surface") == "rpc"]),
            "soroban": len([f for f in fixtures if f.get("surface") == "soroban"]),
        },
        "otherProtocols": {},
        "fixtures": fixtures,
    }


def make_registry(
    fixtures: list[dict],
    *,
    protocol: int = 28,
    version: int = 1,
    digest: str = DIGEST_A,
) -> dict:
    """Build a minimal valid registry document."""
    return {
        "registryVersion": version,
        "protocol": protocol,
        "fixtures": fixtures,
        "packDigest": digest,
    }


class InventoryCompareEdgeTests(unittest.TestCase):
    """Edge cases for diff computation, missing directories, and malformed inputs."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="inventory-edges-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write_json(self, name: str, payload: object) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = compare.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_combined_added_removed_modified_and_matched_fixtures(self) -> None:
        inv_doc = make_inventory(
            [
                make_engine_fixture("p28-same"),
                make_engine_fixture("p28-added", surface="rpc", category="network"),
                make_engine_fixture("p28-modified-surface", surface="soroban", category="smoke"),
                make_engine_fixture("p28-modified-both", surface="rpc", category="fees"),
            ]
        )
        reg_doc = make_registry(
            [
                make_registry_fixture("p28-same"),
                make_registry_fixture("p28-removed", surface="soroban", category="errors"),
                make_registry_fixture("p28-modified-surface", surface="xdr", category="smoke"),
                make_registry_fixture("p28-modified-both", surface="xdr", category="ledger"),
            ]
        )
        inv_path = self.write_json("inventory.json", inv_doc)
        reg_path = self.write_json("registry.json", reg_doc)

        code, out, err = self.run_cli(str(inv_path), str(reg_path), "--format", "json")
        self.assertEqual(code, 1)
        self.assertEqual(err, "")

        report = json.loads(out)
        self.assertFalse(report["match"])
        self.assertEqual(report["matched"], 1)
        self.assertEqual([item["id"] for item in report["extra"]], ["p28-added"])
        self.assertEqual([item["id"] for item in report["missing"]], ["p28-removed"])
        self.assertEqual(
            report["mismatched"],
            [
                {
                    "id": "p28-modified-both",
                    "field": "surface",
                    "inventory": "rpc",
                    "registry": "xdr",
                },
                {
                    "id": "p28-modified-both",
                    "field": "category",
                    "inventory": "fees",
                    "registry": "ledger",
                },
                {
                    "id": "p28-modified-surface",
                    "field": "surface",
                    "inventory": "soroban",
                    "registry": "xdr",
                },
            ],
        )

    def test_empty_inventories_match_and_nonempty_sides_diff_cleanly(self) -> None:
        empty_inv = self.write_json("empty-inv.json", make_inventory([]))
        empty_reg = self.write_json("empty-reg.json", make_registry([]))
        code, out, err = self.run_cli(str(empty_inv), str(empty_reg))
        self.assertEqual(code, 0, err)
        self.assertIn("OK: both inventories hold the same 0 fixture(s)", out)

        pop_inv = self.write_json("pop-inv.json", make_inventory([make_engine_fixture("p28-z"), make_engine_fixture("p28-a")]))
        code, out, _ = self.run_cli(str(pop_inv), str(empty_reg), "--format", "json")
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual([item["id"] for item in report["extra"]], ["p28-a", "p28-z"])
        self.assertEqual(report["missing"], [])

    def test_absent_protocol_directory_reports_diagnostic_without_crashing(self) -> None:
        missing_dir_inv = self.write_json(
            "missing-dir-inv.json", make_inventory([], directory_found=False)
        )
        reg_path = self.write_json("reg.json", make_registry([]))

        code, out, err = self.run_cli(str(missing_dir_inv), str(reg_path))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(str(missing_dir_inv), err)
        self.assertIn("'directoryFound' is false", err)

    def test_malformed_json_and_invalid_utf8_capture_file_diagnostics(self) -> None:
        reg_path = self.write_json("reg.json", make_registry([]))

        malformed = self.tmp / "malformed.json"
        malformed.write_text('{"inventoryVersion": 1, "protocol": ', encoding="utf-8")
        code, _, err = self.run_cli(str(malformed), str(reg_path))
        self.assertEqual(code, 2)
        self.assertIn(str(malformed), err)
        self.assertIn("is not valid JSON", err)

        bad_utf8 = self.tmp / "bad-utf8.json"
        bad_utf8.write_bytes(b"\xff\xfe\x00")
        code, _, err = self.run_cli(str(bad_utf8), str(reg_path))
        self.assertEqual(code, 2)
        self.assertIn(str(bad_utf8), err)
        self.assertIn("is not valid UTF-8", err)

        inv_path = self.write_json("inv.json", make_inventory([]))
        malformed_reg = self.tmp / "malformed-reg.json"
        malformed_reg.write_text('["not", "an", "object"]', encoding="utf-8")
        code, _, err = self.run_cli(str(inv_path), str(malformed_reg))
        self.assertEqual(code, 2)
        self.assertIn(str(malformed_reg), err)
        self.assertIn("a registry must be a JSON object", err)

    def test_missing_metadata_fields_and_contradictory_counts_fail_cleanly(self) -> None:
        incomplete_inv = make_inventory([])
        del incomplete_inv["counts"]
        del incomplete_inv["protocol"]
        problems = compare.check_inventory(incomplete_inv)
        self.assertTrue(any("'protocol'" in p for p in problems), problems)
        self.assertTrue(any("'counts'" in p for p in problems), problems)

        bad_count_inv = make_inventory([make_engine_fixture("p28-a")], total=99)
        problems = compare.check_inventory(bad_count_inv)
        self.assertTrue(any("contradicts itself" in p for p in problems), problems)

        incomplete_reg = make_registry([make_registry_fixture("p28-a")])
        del incomplete_reg["packDigest"]
        del incomplete_reg["fixtures"][0]["description"]
        reg_problems = compare.check_registry(incomplete_reg)
        self.assertTrue(any("packDigest" in p for p in reg_problems), reg_problems)
        self.assertTrue(any("description" in p for p in reg_problems), reg_problems)

    def test_missing_paths_and_protocol_mismatch_exit_two_with_context(self) -> None:
        inv_28 = self.write_json("inv28.json", make_inventory([], protocol=28))
        reg_29 = self.write_json("reg29.json", make_registry([], protocol=29))

        code, _, err = self.run_cli(str(inv_28), str(reg_29))
        self.assertEqual(code, 2)
        self.assertIn("protocol 28", err)
        self.assertIn("protocol 29", err)

        absent_inv = self.tmp / "does-not-exist.json"
        code, _, err = self.run_cli(str(absent_inv), str(reg_29))
        self.assertEqual(code, 2)
        self.assertIn(str(absent_inv), err)
        self.assertIn("no such engine inventory file", err)

        code, _, err = self.run_cli(str(self.tmp), str(reg_29))
        self.assertEqual(code, 2)
        self.assertTrue(
            "is a directory" in err or "could not be read" in err,
            err,
        )


if __name__ == "__main__":
    unittest.main()
