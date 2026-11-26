"""Strict enforcement tests for tools/validate/check_root_files.py (issue #673).

Note: in ``tools/validate/check_root_files.py``, the root allow-list constant is
``DEFAULT_ALLOWLIST`` (not ``ALLOWED_ROOT_ENTRIES``), and ``main()`` reports
offending entries on stderr under ``ERROR: Unexpected file(s) found in
repository root:`` without printing the constant name. Also note that the
non-git filesystem fallback in ``get_root_entries()`` ignores ``.DS_Store``,
whereas ``git ls-files`` (used inside git worktrees), ``is_allowed()``, and
``check_root_entries()`` strictly reject ``.DS_Store`` and all unlisted
dotfiles and backup extensions.

Run with: python3 -m unittest tests/test_check_root_files_enforcement.py
"""
from __future__ import annotations

import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validate import check_root_files

SCRIPT_PATH = REPO_ROOT / "tools" / "validate" / "check_root_files.py"


class CheckRootFilesEnforcementTests(unittest.TestCase):
    """Verify strict root allow-list enforcement across files, dotfiles, and dirs."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="root-guard-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _init_git_repo(self) -> Path:
        repo = self.tmp / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        (repo / "README.md").write_text("# test repo\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True
        )
        return repo

    def test_current_repository_root_passes_with_exit_zero(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check_root_files.main([])
        self.assertEqual(code, 0, err.getvalue())
        self.assertIn("OK: all root entries match allow-list", out.getvalue())
        self.assertEqual(err.getvalue(), "")

        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK: all root entries match allow-list", proc.stdout)

    def test_default_allowlist_and_protocol_pack_pattern_enforcement(self) -> None:
        for required in ("README.md", "CONTRIBUTING.md", "Makefile", "schemas", "tests", "tools"):
            self.assertIn(required, check_root_files.DEFAULT_ALLOWLIST)
            self.assertTrue(check_root_files.is_allowed(required))

        self.assertTrue(check_root_files.is_allowed("protocol-27"))
        self.assertTrue(check_root_files.is_allowed("protocol-31"))
        self.assertFalse(check_root_files.is_allowed("protocol-"))
        self.assertFalse(check_root_files.is_allowed("protocol-28-extra"))
        self.assertFalse(check_root_files.is_allowed("protocol-next"))

    def test_unauthorized_files_dotfiles_and_backup_extensions_rejected(self) -> None:
        unauthorized = [
            ".DS_Store",
            ".env",
            ".README.md.swp",
            "README.md~",
            "backup.tar",
            "temp.txt",
            "unlisted.sh",
        ]
        for entry in unauthorized:
            with self.subTest(entry=entry):
                self.assertFalse(check_root_files.is_allowed(entry))

        self.assertEqual(
            check_root_files.check_root_entries(["README.md", *unauthorized]),
            sorted(unauthorized),
        )

        repo = self._init_git_repo()
        for entry in unauthorized:
            (repo / entry).write_text("stray\n", encoding="utf-8")

        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check_root_files.main(["--root", str(repo)])

        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        stderr_text = err.getvalue()
        self.assertIn("ERROR: Unexpected file(s) found in repository root:", stderr_text)
        for entry in unauthorized:
            self.assertIn(f"  - {entry}", stderr_text)

    def test_unauthorized_root_directories_fail_validation(self) -> None:
        repo = self._init_git_repo()
        (repo / "scratch_dir").mkdir()
        (repo / "scratch_dir" / "notes.txt").write_text("temp\n", encoding="utf-8")
        (repo / ".vscode").mkdir()
        (repo / ".vscode" / "settings.json").write_text("{}\n", encoding="utf-8")
        (repo / "protocol-28-copy").mkdir()
        (repo / "protocol-28-copy" / "a.toml").write_text("id = 'x'\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--root", str(repo)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("ERROR: Unexpected file(s) found in repository root:", proc.stderr)
        for dirname in ("scratch_dir", ".vscode", "protocol-28-copy"):
            self.assertIn(f"  - {dirname}", proc.stderr)


if __name__ == "__main__":
    unittest.main()
