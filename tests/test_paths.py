"""Tests for tools/common/paths.py.

Run with: python3 -m unittest tests/test_paths.py
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.common import paths


class PathUtilityTests(unittest.TestCase):
    def make_symlink(self, target: Path, link: Path, *, directory: bool = False) -> None:
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links are unavailable: {error}")

    def make_hardlink(self, target: Path, link: Path) -> None:
        try:
            os.link(target, link)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"hard links are unavailable: {error}")

    def test_canonical_path_normalizes_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            file_path = Path(temporary) / "fixture.toml"
            file_path.write_text("fixture", encoding="utf-8")

            self.assertEqual(
                paths.canonical_path(file_path),
                os.path.normcase(os.path.realpath(str(file_path))),
            )

    def test_canonical_path_resolves_single_and_nested_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_directory = root / "real"
            real_directory.mkdir()
            real_file = real_directory / "fixture.toml"
            real_file.write_text("fixture", encoding="utf-8")

            directory_link = root / "directory-link"
            self.make_symlink(real_directory, directory_link, directory=True)
            single_link = directory_link / "single-link.toml"
            self.make_symlink(real_file, single_link)

            nested_link = root / "nested-link.toml"
            self.make_symlink(single_link, nested_link)

            expected = paths.canonical_path(real_file)
            self.assertEqual(paths.canonical_path(single_link), expected)
            self.assertEqual(paths.canonical_path(nested_link), expected)

    def test_canonical_path_resolves_existing_leading_components_for_missing_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_directory = root / "real" / "nested"
            real_directory.mkdir(parents=True)
            directory_link = root / "directory-link"
            self.make_symlink(root / "real", directory_link, directory=True)

            missing_via_link = directory_link / "nested" / "future.toml"
            missing_real_path = real_directory / "future.toml"

            self.assertFalse(missing_via_link.exists())
            self.assertEqual(
                paths.canonical_path(missing_via_link),
                paths.canonical_path(missing_real_path),
            )

    def test_canonical_path_uses_platform_normcase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            file_path = Path(temporary) / "fixture.toml"
            file_path.write_text("fixture", encoding="utf-8")
            real_path = os.path.realpath(str(file_path))
            expected = os.path.normcase(real_path)

            with (
                mock.patch.object(paths.os.path, "realpath", return_value=real_path) as realpath,
                mock.patch.object(paths.os.path, "normcase", wraps=os.path.normcase) as normcase,
            ):
                result = paths.canonical_path(file_path)

            self.assertEqual(result, expected)
            realpath.assert_called_once_with(str(file_path))
            normcase.assert_called_once_with(real_path)

    def test_is_same_file_detects_hardlink_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.toml"
            hardlink = root / "hardlink.toml"
            original.write_text("fixture", encoding="utf-8")
            self.make_hardlink(original, hardlink)

            self.assertTrue(paths.is_same_file(original, hardlink))

    def test_is_same_file_detects_identical_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.toml"
            first_link = root / "first-link.toml"
            second_link = root / "second-link.toml"
            original.write_text("fixture", encoding="utf-8")
            self.make_symlink(original, first_link)
            self.make_symlink(original, second_link)

            self.assertTrue(paths.is_same_file(first_link, second_link))

    def test_is_same_file_detects_duplicate_nonexistent_canonical_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_directory = root / "real"
            real_directory.mkdir()
            directory_link = root / "directory-link"
            self.make_symlink(real_directory, directory_link, directory=True)

            real_missing = real_directory / "future.toml"
            linked_missing = directory_link / "future.toml"

            self.assertFalse(real_missing.exists())
            self.assertTrue(paths.is_same_file(real_missing, linked_missing))

    def test_is_same_file_rejects_distinct_files_with_same_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first" / "fixture.toml"
            second = root / "second" / "fixture.toml"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")

            self.assertFalse(paths.is_same_file(first, second))


if __name__ == "__main__":
    unittest.main()
