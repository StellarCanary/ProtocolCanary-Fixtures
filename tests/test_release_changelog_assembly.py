"""Changelog fragment assembly and validation tests (issue #671).

Tests tools/release/changelog.py and fragment validation rules in
tools/validate/check_changelog.py using isolated temporary directories.

Stdlib only: the CI ``validate`` job runs ``unittest discover`` on a bare
interpreter.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.release import changelog  # noqa: E402
from tools.validate import check_changelog  # noqa: E402


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


class ReleaseChangelogAssemblyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="changelog-assembly-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "--quiet")
        _git(self.root, "config", "user.name", "Changelog Assembly Test")
        _git(self.root, "config", "user.email", "changelog@example.invalid")
        (self.root / "README.md").write_text("isolated test repo\n", encoding="utf-8")
        _git(self.root, "add", "README.md")
        _git(self.root, "commit", "--quiet", "-m", "baseline")

    def _write_fragment(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _commit_all(self, message: str = "update fragments") -> None:
        _git(self.root, "add", ".")
        _git(self.root, "commit", "--quiet", "-m", message)

    def test_discovers_and_sorts_fragments_across_protocol_and_common_directories(self) -> None:
        self._write_fragment("changelog.d/protocol-28/20-feature.md", "- Added XDR fixture.\n")
        self._write_fragment("changelog.d/common/02-shared.md", "- Updated shared helper.\n")
        self._write_fragment("changelog.d/protocol-28/01-bugfix.md", "- Fixed edge case.\n")
        self._write_fragment("changelog.d/common/01-infra.md", "- Improved validator.\n")
        self._write_fragment("changelog.d/protocol-29/only-p29.md", "- Protocol 29 only note.\n")
        self._write_fragment("changelog.d/protocol-30/only-p30.md", "- Protocol 30 only note.\n")
        self._commit_all("initial fragments")

        paths = changelog.fragment_paths(self.root, 28, "1.0.0")
        self.assertEqual(
            paths,
            [
                "changelog.d/common/01-infra.md",
                "changelog.d/common/02-shared.md",
                "changelog.d/protocol-28/01-bugfix.md",
                "changelog.d/protocol-28/20-feature.md",
            ],
        )

        notes = changelog.render_changelog(self.root, 28, "1.0.0")
        self.assertTrue(notes.startswith("# Protocol 28 fixture pack 1.0.0\n\n## Changes\n\n"))
        expected_sections = ["### 01-infra", "### 02-shared", "### 01-bugfix", "### 20-feature"]
        positions = [notes.index(section) for section in expected_sections]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Protocol 29 only note", notes)
        self.assertNotIn("Protocol 30 only note", notes)

    def test_incremental_release_includes_only_fragments_added_after_previous_tag(self) -> None:
        self._write_fragment("changelog.d/common/old-common.md", "- Old common change.\n")
        self._write_fragment("changelog.d/protocol-29/v1-note.md", "- Released in 1.0.0.\n")
        self._commit_all("v1.0.0 fragments")
        _git(self.root, "tag", "fixtures-p29-v1.0.0")

        self._write_fragment("changelog.d/protocol-29/v11-note.md", "- Added for 1.1.0.\n")
        self._write_fragment("changelog.d/common/new-common.md", "- New common change.\n")
        self._commit_all("v1.1.0 fragments")

        notes = changelog.render_changelog(self.root, 29, "1.1.0")
        self.assertIn("### new-common", notes)
        self.assertIn("- New common change.", notes)
        self.assertIn("### v11-note", notes)
        self.assertIn("- Added for 1.1.0.", notes)
        self.assertNotIn("Released in 1.0.0", notes)
        self.assertNotIn("Old common change", notes)

    def test_empty_or_absent_fragment_directories_produce_clean_release_notes(self) -> None:
        # No changelog.d/ directory at all
        absent_notes = changelog.render_changelog(self.root, 28, "0.1.0")
        self.assertEqual(
            absent_notes,
            "# Protocol 28 fixture pack 0.1.0\n\n## Changes\n\n"
            "No changelog fragments are recorded for this pack yet.\n",
        )

        # Empty subdirectories present
        (self.root / "changelog.d" / "common").mkdir(parents=True)
        (self.root / "changelog.d" / "protocol-28").mkdir(parents=True)
        empty_dir_notes = changelog.render_changelog(self.root, 28, "0.1.0")
        self.assertEqual(empty_dir_notes, absent_notes)

        # Prior tag exists, no new fragments added
        _git(self.root, "tag", "fixtures-p28-v0.1.0")
        since_notes = changelog.render_changelog(self.root, 28, "0.2.0")
        self.assertEqual(
            since_notes,
            "# Protocol 28 fixture pack 0.2.0\n\n## Changes\n\n"
            "No changelog fragments were added since `fixtures-p28-v0.1.0`.\n",
        )

    def test_empty_and_whitespace_only_fragments_fail_validation_and_assembly(self) -> None:
        for name, body in (("empty.md", ""), ("whitespace.md", "   \n\t\n  ")):
            with self.subTest(fragment=name):
                rel = f"changelog.d/protocol-28/{name}"
                self._write_fragment(rel, body)
                with self.assertRaisesRegex(changelog.ChangelogError, "fragment is empty"):
                    changelog.render_changelog(self.root, 28, "1.0.0")

                check_res = check_changelog.check_changelog(
                    changed_files=["protocol-28/xdr/sample.toml", rel],
                    repo_root=self.root,
                )
                self.assertFalse(check_res.passed)
                self.assertIn("non-empty UTF-8 Markdown", check_res.message)

                # Clean up before next subtest iteration
                (self.root / rel).unlink()

    def test_invalid_fragment_filenames_and_non_utf8_content_are_rejected(self) -> None:
        for bad_name in ("UPPERCASE.md", ".hidden.md", "-leading-dash.md", "nested/sub.md"):
            with self.subTest(filename=bad_name):
                rel = f"changelog.d/protocol-28/{bad_name}"
                self._write_fragment(rel, "- Valid body.\n")
                with self.assertRaisesRegex(changelog.ChangelogError, "invalid changelog fragment path"):
                    changelog.render_changelog(self.root, 28, "1.0.0")
                (self.root / rel).unlink()

        bad_utf8 = self.root / "changelog.d" / "protocol-28" / "bad-encoding.md"
        bad_utf8.parent.mkdir(parents=True, exist_ok=True)
        bad_utf8.write_bytes(b"\xff\xfe\xfd")
        with self.assertRaisesRegex(changelog.ChangelogError, "cannot read fragment safely"):
            changelog.render_changelog(self.root, 28, "1.0.0")

    def test_check_changelog_exempts_tests_and_validates_fragment_paths(self) -> None:
        self.assertTrue(check_changelog.is_changelog_file("changelog.d/common/valid-note.md"))
        self.assertTrue(check_changelog.is_changelog_file("changelog.d/protocol-30/p30-note.md"))
        self.assertFalse(check_changelog.is_changelog_file("changelog.d/unknown/note.md"))
        self.assertFalse(check_changelog.is_changelog_file("CHANGELOG.md"))

        tests_only = check_changelog.check_changelog(
            changed_files=["tests/test_release_changelog_assembly.py"],
            repo_root=self.root,
        )
        self.assertTrue(tests_only.passed)
        self.assertEqual(tests_only.governed_files, [])

        self._write_fragment("changelog.d/protocol-28/valid-change.md", "- Documented change.\n")
        governed_ok = check_changelog.check_changelog(
            changed_files=["tools/release/changelog.py", "changelog.d/protocol-28/valid-change.md"],
            repo_root=self.root,
            added_fragments=["changelog.d/protocol-28/valid-change.md"],
        )
        self.assertTrue(governed_ok.passed)

    def test_cli_writes_markdown_or_exits_nonzero_on_error(self) -> None:
        self._write_fragment("changelog.d/protocol-28/cli-entry.md", "- Added CLI coverage.\n")
        self._commit_all("cli fragment")
        out_path = self.root / "release-notes" / "NOTES.md"

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = changelog.main(
                [
                    "--protocol",
                    "28",
                    "--version",
                    "1.2.3",
                    "--output",
                    str(out_path),
                    "--repo-root",
                    str(self.root),
                ]
            )
        self.assertEqual(code, 0)
        self.assertIn("OK: wrote", stdout.getvalue())
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("# Protocol 28 fixture pack 1.2.3", content)
        self.assertIn("### cli-entry", content)
        self.assertIn("- Added CLI coverage.", content)

        # Invalid empty fragment via CLI must fail without writing output
        self._write_fragment("changelog.d/protocol-28/zz-empty.md", "   \n")
        self._commit_all("empty fragment")
        fail_out = self.root / "release-notes" / "FAIL.md"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            fail_code = changelog.main(
                [
                    "--protocol",
                    "28",
                    "--version",
                    "1.2.3",
                    "--output",
                    str(fail_out),
                    "--repo-root",
                    str(self.root),
                ]
            )
        self.assertEqual(fail_code, 1)
        self.assertIn("fragment is empty", stderr.getvalue())
        self.assertFalse(fail_out.exists())


if __name__ == "__main__":
    unittest.main()
