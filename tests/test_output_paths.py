"""Tests for output path collision guards and safety (F-117, issue #410).

Ensures tools/registry/generate.py and tools/release/manifest.py refuse
output targets that would overwrite input fixtures, payloads, pack directories,
or release archives, including through aliases (symlinks, hard links, .., normcase).
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_support as support

from tools.common import paths
from tools.pack import pack
from tools.registry import generate
from tools.release import manifest


class TestPathSafetyHelper(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_canonical_path_normalizes_and_resolves_symlinks(self) -> None:
        target = self.root / "sub" / ".." / "file.txt"
        canon = paths.canonical_path(target)
        self.assertEqual(canon, os.path.normcase(os.path.realpath(str(target))))

    def test_is_same_file_existing_and_nonexistent(self) -> None:
        f1 = self.root / "f1.txt"
        f1.write_text("a", encoding="utf-8")
        f2 = self.root / "sub" / ".." / "f1.txt"
        self.assertTrue(paths.is_same_file(f1, f2))

        nonexistent1 = self.root / "sub" / ".." / "new.txt"
        nonexistent2 = self.root / "new.txt"
        self.assertTrue(paths.is_same_file(nonexistent1, nonexistent2))

    def test_check_target_safety_refuses_directory(self) -> None:
        d = self.root / "somedir"
        d.mkdir()
        with self.assertRaisesRegex(ValueError, "target is a directory"):
            paths.check_target_safety(d, [])

    def test_check_target_safety_collision_message(self) -> None:
        f = self.root / "fixture.toml"
        f.write_text("content", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            paths.check_target_safety(f, [(f, "a pack fixture")])
        self.assertIn("refusing to write", str(caught.exception))
        self.assertIn("it is the same file as a pack fixture", str(caught.exception))


class TestRegistryGeneratorOutputSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        # Build a valid minimal pack with a fixture and a payload
        self.pack_dir = self.root / "protocol-28"
        self.pack_dir.mkdir()
        rpc_dir = self.pack_dir / "rpc"
        rpc_dir.mkdir()

        self.payload = rpc_dir / "sample.bin"
        self.payload.write_bytes(b"payload data")

        self.fixture = rpc_dir / "p28-rpc-test.toml"
        self.fixture.write_text(
            """id = "p28-rpc-test"
protocol = 28
surface = "rpc"
category = "smoke"
description = "test"
source_reference = "CAP-0083"
input_file = "sample.bin"

[expect]
kind = "rpc-response"
""",
            encoding="utf-8",
        )
        self.fixture_bytes = self.fixture.read_bytes()
        self.payload_bytes = self.payload.read_bytes()

    def run_generate(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = generate.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_default_registry_output_is_stdout_only(self) -> None:
        code, out, err = self.run_generate(str(self.pack_dir))
        self.assertEqual(code, 0, err)
        default_output = self.pack_dir / "registry-v1.json"
        self.assertFalse(default_output.exists())
        self.assertIn('"registryVersion": 1', out)

        code2, out2, err2 = self.run_generate(str(self.pack_dir))
        self.assertEqual(code2, 0, err2)
        self.assertEqual(out2, out)
        self.assertFalse(default_output.exists())

    def test_output_to_fresh_path_allowed(self) -> None:
        fresh = self.root / "out" / "custom_reg.json"
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(fresh))
        self.assertEqual(code, 0, err)
        self.assertTrue(fresh.is_file())

    def test_stdout_allowed(self) -> None:
        code, out, err = self.run_generate(str(self.pack_dir), "--stdout")
        self.assertEqual(code, 0, err)
        self.assertIn('"registryVersion": 1', out)

    def test_refuses_overwriting_fixture_direct_path(self) -> None:
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(self.fixture))
        self.assertEqual(code, 1)
        self.assertIn("registry output must be outside the pack directory", err)
        self.assertIn("FAILED: no registry written", err)
        self.assertEqual(self.fixture.read_bytes(), self.fixture_bytes)

    def test_refuses_overwriting_fixture_relative_path(self) -> None:
        rel_fixture = self.pack_dir / "rpc" / ".." / "rpc" / "p28-rpc-test.toml"
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(rel_fixture))
        self.assertEqual(code, 1)
        self.assertIn("registry output must be outside the pack directory", err)
        self.assertIn("FAILED: no registry written", err)
        self.assertEqual(self.fixture.read_bytes(), self.fixture_bytes)

    def test_refuses_overwriting_fixture_via_symlink(self) -> None:
        sym = self.root / "sym_fixture.toml"
        try:
            os.symlink(self.fixture, sym)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not support symlinks")
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(sym))
        self.assertEqual(code, 1)
        self.assertIn("registry output must be outside the pack directory", err)
        self.assertEqual(self.fixture.read_bytes(), self.fixture_bytes)

    def test_refuses_overwriting_fixture_via_symlink_directory(self) -> None:
        sym_dir = self.root / "sym_rpc"
        try:
            os.symlink(self.pack_dir / "rpc", sym_dir)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not support directory symlinks")
        target = sym_dir / "p28-rpc-test.toml"
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(target))
        self.assertEqual(code, 1)
        self.assertIn("registry output must be outside the pack directory", err)
        self.assertEqual(self.fixture.read_bytes(), self.fixture_bytes)

    def test_refuses_overwriting_fixture_via_hardlink(self) -> None:
        hard = self.root / "hard_fixture.toml"
        try:
            os.link(self.fixture, hard)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not support hard links")
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(hard))
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("it is the same file as a pack fixture", err)
        self.assertEqual(self.fixture.read_bytes(), self.fixture_bytes)

    def test_refuses_output_equal_to_pack_directory(self) -> None:
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(self.pack_dir))
        self.assertEqual(code, 1)
        self.assertIn("registry output must be outside the pack directory", err)
        self.assertTrue(self.pack_dir.is_dir())

    def test_refuses_output_equal_to_payload_file(self) -> None:
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(self.payload))
        self.assertEqual(code, 1)
        self.assertIn("registry output must be outside the pack directory", err)
        self.assertEqual(self.payload.read_bytes(), self.payload_bytes)

    def test_refuses_existing_directory_target(self) -> None:
        some_dir = self.root / "existing_dir"
        some_dir.mkdir()
        code, out, err = self.run_generate(str(self.pack_dir), "--output", str(some_dir))
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("target is a directory", err)


class TestReleaseManifestOutputSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        support.write_pack(self.root)
        self.info = pack.build_archive(self.root / "pack", self.root / "out", "1.4.2")
        self.archive = self.info.path
        self.archive_bytes = self.archive.read_bytes()

    def run_manifest(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = manifest.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_default_manifest_next_to_archive_allowed(self) -> None:
        code, out, err = self.run_manifest(str(self.archive), "--revision", support.REVISION)
        self.assertEqual(code, 0, err)
        manifest_path = self.archive.with_name("protocolcanary-fixtures-1.4.2.manifest.json")
        self.assertTrue(manifest_path.is_file())

    def test_explicit_manifest_and_different_sha256_allowed(self) -> None:
        out_manifest = self.root / "custom.manifest.json"
        out_sha = self.root / "custom.sha256"
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(out_manifest),
            "--sha256-file",
            str(out_sha),
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(out_manifest.is_file())
        self.assertTrue(out_sha.is_file())

    def test_refuses_output_equal_to_archive_direct(self) -> None:
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(self.archive),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("it is the same file as the release archive", err)
        self.assertIn("FAILED: no manifest written", err)
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)

    def test_refuses_output_equal_to_archive_via_symlink(self) -> None:
        sym = self.root / "sym_archive.tar.gz"
        try:
            os.symlink(self.archive, sym)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not support symlinks")
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(sym),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("it is the same file as the release archive", err)
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)

    def test_refuses_output_equal_to_archive_via_hardlink(self) -> None:
        hard = self.root / "hard_archive.tar.gz"
        try:
            os.link(self.archive, hard)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not support hard links")
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(hard),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("it is the same file as the release archive", err)
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)

    def test_refuses_sha256_file_equal_to_archive(self) -> None:
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--sha256-file",
            str(self.archive),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("it is the same file as the release archive", err)
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)

    def test_refuses_output_and_sha256_file_same_target(self) -> None:
        target = self.root / "same_target.txt"
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(target),
            "--sha256-file",
            str(target),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("--output and --sha256-file name the same file", err)
        self.assertFalse(target.exists())

    def test_refuses_output_and_sha256_file_via_symlink(self) -> None:
        t1 = self.root / "file1.txt"
        t1.write_text("orig", encoding="utf-8")
        sym1 = self.root / "sym1.txt"
        try:
            os.symlink(t1, sym1)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not support symlinks")
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(t1),
            "--sha256-file",
            str(sym1),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("--output and --sha256-file name the same file", err)

    def test_refuses_existing_directory_target(self) -> None:
        d = self.root / "dest_dir"
        d.mkdir()
        code, out, err = self.run_manifest(
            str(self.archive),
            "--revision",
            support.REVISION,
            "--output",
            str(d),
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing to write", err)
        self.assertIn("target is a directory", err)


class TestParentTraversalOutputPaths(unittest.TestCase):
    """Issue #597: output path resolver behaviour with relative ``..`` traversal.

    ``tools/common/paths.canonical_path`` uses ``os.path.realpath`` so it
    resolves every ``..`` segment, including chains that escape the directory
    the path starts under.  ``check_target_safety`` then compares the resolved
    target against each protected input, so a path that navigates *into* a
    protected file through any number of ``..`` hops is still caught.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    # ---- canonical_path with multiple traversals ----------------------------

    def test_canonical_path_resolves_multiple_parent_references(self) -> None:
        # Three levels up from a/b/c then back in: a/b/c/../../../sibling
        # resolves to <root>/sibling, not to something that keeps the ``..``.
        (self.root / "a" / "b" / "c").mkdir(parents=True)
        path = self.root / "a" / "b" / "c" / ".." / ".." / ".." / "other.txt"
        expected = os.path.normcase(
            os.path.realpath(str(self.root / "other.txt"))
        )
        self.assertEqual(paths.canonical_path(path), expected)
        self.assertNotIn("..", paths.canonical_path(path))

    def test_canonical_path_resolves_to_root_via_many_ups(self) -> None:
        # a/b/../.. collapses back to <root>, deterministically.
        (self.root / "a" / "b").mkdir(parents=True)
        path = self.root / "a" / "b" / ".." / ".."
        expected = os.path.normcase(os.path.realpath(str(self.root)))
        self.assertEqual(paths.canonical_path(path), expected)

    def test_canonical_path_escape_resolves_deterministically_outside_root(self) -> None:
        # Enough ``..`` segments to escape the temp directory entirely.
        # The result must be a consistent absolute path with no ``..`` in it.
        path = self.root / ".." / ".." / ".." / "escape.txt"
        result = paths.canonical_path(path)
        self.assertNotIn("..", result)
        # The escaped path differs from the same filename inside the root.
        inside = paths.canonical_path(self.root / "escape.txt")
        self.assertNotEqual(result, inside)

    def test_safe_subpath_with_traversal_resolves_deterministically(self) -> None:
        # sub/a/../b/out.json and sub/b/out.json identify the same location.
        (self.root / "sub" / "a").mkdir(parents=True)
        (self.root / "sub" / "b").mkdir()
        path1 = self.root / "sub" / "a" / ".." / "b" / "out.json"
        path2 = self.root / "sub" / "b" / "out.json"
        self.assertEqual(paths.canonical_path(path1), paths.canonical_path(path2))

    # ---- check_target_safety with deep traversals ---------------------------

    def test_check_target_safety_catches_fixture_via_two_level_traversal(self) -> None:
        # sub/deep/../../sub/fixture.toml ultimately resolves to sub/fixture.toml.
        (self.root / "sub" / "deep").mkdir(parents=True)
        f = self.root / "sub" / "fixture.toml"
        f.write_text("content", encoding="utf-8")
        traversal = (
            self.root / "sub" / "deep" / ".." / ".." / "sub" / "fixture.toml"
        )
        with self.assertRaises(ValueError) as caught:
            paths.check_target_safety(traversal, [(f, "a pack fixture")])
        self.assertIn("refusing to write", str(caught.exception))

    def test_check_target_safety_catches_fixture_via_three_level_traversal(self) -> None:
        # Navigate three levels up from deep inside the tree to reach the fixture.
        (self.root / "sub" / "a" / "b").mkdir(parents=True)
        protected = self.root / "important.toml"
        protected.write_text("important", encoding="utf-8")
        traversal = (
            self.root / "sub" / "a" / "b" / ".." / ".." / ".." / "important.toml"
        )
        with self.assertRaises(ValueError):
            paths.check_target_safety(traversal, [(protected, "a release archive")])

    def test_safe_path_with_traversal_is_allowed_when_it_misses_protected_files(self) -> None:
        # If the traversal resolves to a *different* path, no error is raised.
        (self.root / "sub" / "a").mkdir(parents=True)
        protected = self.root / "fixture.toml"
        protected.write_text("content", encoding="utf-8")
        # sub/a/../out.json resolves to sub/out.json — not the protected file.
        safe_target = self.root / "sub" / "a" / ".." / "out.json"
        # Should not raise.
        paths.check_target_safety(safe_target, [(protected, "a pack fixture")])

    def test_path_escaping_to_sibling_directory_is_rejected_when_matching(self) -> None:
        # An output path that uses ``..`` to escape the pack directory and
        # land on the archive is still caught by identity comparison.
        (self.root / "pack" / "rpc").mkdir(parents=True)
        archive = self.root / "releases" / "out.tar.gz"
        archive.parent.mkdir()
        archive.write_bytes(b"fake archive data")
        # Navigate from inside pack/ up two levels and into releases/.
        traversal = (
            self.root / "pack" / "rpc" / ".." / ".." / "releases" / "out.tar.gz"
        )
        with self.assertRaises(ValueError) as caught:
            paths.check_target_safety(traversal, [(archive, "the release archive")])
        self.assertIn("refusing to write", str(caught.exception))

    # ---- registry generator with multi-level traversal paths ----------------

    def test_registry_generator_refuses_fixture_via_deep_traversal(self) -> None:
        # Provide a deep ``..``-traversal path that resolves to the fixture.
        # The generator's output-safety check must still reject it.
        import contextlib
        import io as _io

        from tools.registry import generate

        tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(tmp2.cleanup)
        root2 = Path(tmp2.name)

        pack_dir = root2 / "protocol-28"
        pack_dir.mkdir()
        rpc_dir = pack_dir / "rpc"
        rpc_dir.mkdir()
        payload = rpc_dir / "sample.bin"
        payload.write_bytes(b"payload")
        fixture = rpc_dir / "p28-rpc-deep.toml"
        fixture.write_text(
            'id = "p28-rpc-deep"\nprotocol = 28\nsurface = "rpc"\n'
            'category = "smoke"\ndescription = "traversal test"\n'
            'source_reference = "CAP-0083"\n\n[expect]\nkind = "rpc-response"\n',
            encoding="utf-8",
        )
        fixture_bytes = fixture.read_bytes()

        # rpc/subdir/../../rpc/p28-rpc-deep.toml resolves to the fixture.
        (rpc_dir / "subdir").mkdir()
        traversal = rpc_dir / "subdir" / ".." / ".." / "rpc" / "p28-rpc-deep.toml"

        out, err = _io.StringIO(), _io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = generate.main([str(pack_dir), "--output", str(traversal)])
        self.assertEqual(code, 1)
        self.assertEqual(fixture.read_bytes(), fixture_bytes)


if __name__ == "__main__":
    unittest.main()
