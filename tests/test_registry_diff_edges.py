"""Edge-case and diagnostic tests for tools/registry/diff.py.

Run with: python3 -m unittest tests/test_registry_diff_edges.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIFF_PATH = REPO_ROOT / "tools" / "registry" / "diff.py"

_spec = importlib.util.spec_from_file_location("registry_diff_edges_target", DIFF_PATH)
diff = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["registry_diff_edges_target"] = diff
_spec.loader.exec_module(diff)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64


def _fixture(
    identifier: str,
    path: str,
    sha256: str,
    surface: str = "xdr",
) -> dict:
    return {
        "id": identifier,
        "path": path,
        "sha256": sha256,
        "surface": surface,
        "category": "cap-0083",
        "description": f"fixture {identifier}",
        "payloads": [],
    }


def _registry(
    fixtures: list[dict],
    protocol: int = 29,
    digest: str = DIGEST_A,
    version: int = 1,
) -> dict:
    return {
        "registryVersion": version,
        "protocol": protocol,
        "fixtures": fixtures,
        "packDigest": digest,
    }


def _write_json(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


class RegistryDiffEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="registry-diff-edges-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _run_cli(self, *argv: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = diff.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_identical_registries_return_zero_with_clean_summaries(self) -> None:
        doc = _registry(
            [
                _fixture("p29-a", "xdr/a.toml", SHA_A),
                _fixture("p29-b", "rpc/b.toml", SHA_B, surface="rpc"),
            ],
            digest=DIGEST_A,
        )
        old_path = _write_json(self.tmp / "old.json", doc)
        new_path = _write_json(self.tmp / "new.json", doc)

        code_text, out_text, err_text = self._run_cli(str(old_path), str(new_path))
        self.assertEqual(code_text, 0)
        self.assertEqual(err_text, "")
        self.assertIn("added (0):", out_text)
        self.assertIn("removed (0):", out_text)
        self.assertIn("changed (0):", out_text)
        self.assertIn("moved (0):", out_text)
        self.assertIn("unchanged (2)", out_text)

        code_json, out_json, _ = self._run_cli(
            str(old_path), str(new_path), "--format", "json"
        )
        self.assertEqual(code_json, 0)
        parsed = json.loads(out_json)
        self.assertEqual(parsed["added"], [])
        self.assertEqual(parsed["removed"], [])
        self.assertEqual(parsed["changed"], [])
        self.assertEqual(parsed["moved"], [])
        self.assertEqual(parsed["unchanged"], 2)

        code_md, out_md, _ = self._run_cli(
            str(old_path), str(new_path), "--format", "markdown"
        )
        self.assertEqual(code_md, 0)
        self.assertEqual(out_md, "No fixture changed between the two registries.\n")

    def test_added_removed_changed_and_moved_fixtures_diagnostics(self) -> None:
        old_doc = _registry(
            [
                _fixture("p29-keep", "xdr/keep.toml", SHA_A),
                _fixture("p29-remove", "xdr/remove.toml", SHA_B),
                _fixture("p29-modify", "rpc/modify.toml", SHA_C, surface="rpc"),
                _fixture("p29-move", "soroban/old.toml", SHA_D, surface="soroban"),
            ],
            digest=DIGEST_A,
        )
        new_doc = _registry(
            [
                _fixture("p29-keep", "xdr/keep.toml", SHA_A),
                _fixture("p29-modify", "rpc/modify-renamed.toml", SHA_D, surface="rpc"),
                _fixture("p29-move", "soroban/new.toml", SHA_D, surface="soroban"),
                _fixture("p29-add", "xdr/add.toml", SHA_B),
            ],
            digest=DIGEST_B,
        )
        old_path = _write_json(self.tmp / "old.json", old_doc)
        new_path = _write_json(self.tmp / "new.json", new_doc)

        code, out_json, err = self._run_cli(
            str(old_path), str(new_path), "--format", "json"
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        report = json.loads(out_json)
        self.assertEqual([item["id"] for item in report["added"]], ["p29-add"])
        self.assertEqual([item["id"] for item in report["removed"]], ["p29-remove"])
        self.assertEqual([item["id"] for item in report["changed"]], ["p29-modify"])
        self.assertEqual([item["id"] for item in report["moved"]], ["p29-move"])
        self.assertEqual(report["unchanged"], 1)

        # A fixture with both a changed hash and a changed path is reported as changed, not moved.
        changed = report["changed"][0]
        self.assertEqual(changed["old_path"], "rpc/modify.toml")
        self.assertEqual(changed["new_path"], "rpc/modify-renamed.toml")
        self.assertEqual(changed["old_sha256"], SHA_C)
        self.assertEqual(changed["new_sha256"], SHA_D)

        code_text, out_text, _ = self._run_cli(str(old_path), str(new_path))
        self.assertEqual(code_text, 0)
        self.assertIn("added (1):", out_text)
        self.assertIn("removed (1):", out_text)
        self.assertIn("changed (1):", out_text)
        self.assertIn("moved (1):", out_text)
        self.assertIn("unchanged (1)", out_text)

        code_md, out_md, _ = self._run_cli(
            str(old_path), str(new_path), "--format", "markdown"
        )
        self.assertEqual(code_md, 0)
        self.assertIn("### Added", out_md)
        self.assertIn("### Removed", out_md)
        self.assertIn("### Changed", out_md)
        self.assertIn("### Moved", out_md)

    def test_protocol_version_divergence_requires_override(self) -> None:
        old_path = _write_json(
            self.tmp / "p28.json",
            _registry([_fixture("p28-a", "xdr/a.toml", SHA_A)], protocol=28),
        )
        new_path = _write_json(
            self.tmp / "p29.json",
            _registry([_fixture("p29-a", "xdr/a.toml", SHA_A)], protocol=29),
        )

        code_refused, out_refused, err_refused = self._run_cli(
            str(old_path), str(new_path)
        )
        self.assertEqual(code_refused, 2)
        self.assertEqual(out_refused, "")
        self.assertIn("protocol 28", err_refused)
        self.assertIn("protocol 29", err_refused)
        self.assertIn("--allow-protocol-mismatch", err_refused)

        code_allowed, out_allowed, err_allowed = self._run_cli(
            str(old_path),
            str(new_path),
            "--allow-protocol-mismatch",
            "--format",
            "json",
        )
        self.assertEqual(code_allowed, 0)
        self.assertEqual(err_allowed, "")
        report = json.loads(out_allowed)
        self.assertEqual(report["old"]["protocol"], 28)
        self.assertEqual(report["new"]["protocol"], 29)

    def test_invalid_inputs_and_cli_errors_exit_two(self) -> None:
        valid_path = _write_json(
            self.tmp / "valid.json",
            _registry([_fixture("p29-a", "xdr/a.toml", SHA_A)]),
        )

        # Missing file
        code, out, err = self._run_cli(
            str(valid_path), str(self.tmp / "does-not-exist.json")
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("no such file", err)

        # Directory instead of file (Linux/macOS raises IsADirectoryError; Windows raises PermissionError)
        subdir = self.tmp / "subdir"
        subdir.mkdir()
        code, out, err = self._run_cli(str(valid_path), str(subdir))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue("directory" in err or "could not be read" in err, msg=err)

        # Invalid UTF-8
        bad_utf8 = self.tmp / "bad-utf8.json"
        bad_utf8.write_bytes(b"\xff\xfe\x00")
        code, out, err = self._run_cli(str(valid_path), str(bad_utf8))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("UTF-8", err)

        # Malformed JSON
        malformed = self.tmp / "malformed.json"
        malformed.write_text('{"registryVersion": 1', encoding="utf-8")
        code, out, err = self._run_cli(str(valid_path), str(malformed))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("not valid JSON", err)

        # Empty fixtures list
        empty_fixtures = _write_json(self.tmp / "empty-fixtures.json", _registry([]))
        code, out, err = self._run_cli(str(valid_path), str(empty_fixtures))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("empty", err)

        # Duplicate fixture ID
        duplicate_ids = _write_json(
            self.tmp / "duplicate.json",
            _registry(
                [
                    _fixture("p29-dup", "xdr/a.toml", SHA_A),
                    _fixture("p29-dup", "xdr/b.toml", SHA_B),
                ]
            ),
        )
        code, out, err = self._run_cli(str(valid_path), str(duplicate_ids))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("appears twice", err)

        # Invalid CLI option
        with self.assertRaises(SystemExit) as caught:
            self._run_cli(str(valid_path), str(valid_path), "--format", "yaml")
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
