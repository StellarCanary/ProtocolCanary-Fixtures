"""Extended unit tests for cross-platform portable names and pack path rules (#670).

Covers Windows reserved device names across uppercase/lowercase/mixed casing and
compound extensions, trailing dots and whitespace rejection, forbidden Windows
characters, ASCII control characters (0x00-0x1F) across path components, and
valid cross-platform kebab-case fixture/directory names.

Run with: python3 -m unittest tests/test_portable_names_extended.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.registry import generate

PORTABLE_NAMES_PATH = REPO_ROOT / "tools" / "validate" / "portable_names.py"

_spec = importlib.util.spec_from_file_location(
    "portable_names_extended_under_test", PORTABLE_NAMES_PATH
)
assert _spec is not None and _spec.loader is not None
portable_names = importlib.util.module_from_spec(_spec)
sys.modules["portable_names_extended_under_test"] = portable_names
_spec.loader.exec_module(portable_names)


def is_portable_name(segment: str) -> bool:
    """Boolean wrapper around ``portable_names.check_segment``."""
    try:
        portable_names.check_segment(segment)
    except portable_names.PortableNameError:
        return False
    return True


def validate_portable_names(path: str) -> None:
    """Validate both Windows segment portability and pack control-character rules."""
    portable_names.check_path(path)
    generate.check_pack_path(path)


ALL_WINDOWS_DEVICE_STEMS: tuple[str, ...] = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
)

FORBIDDEN_WINDOWS_CHARS: tuple[str, ...] = (":", "*", "?", '"', "<", ">", "|")


class ExtendedWindowsDeviceNameTests(unittest.TestCase):
    """Rejection of Windows reserved device names across casing and extensions."""

    def test_all_22_reserved_device_names_rejected_across_cases_and_extensions(self) -> None:
        self.assertEqual(len(ALL_WINDOWS_DEVICE_STEMS), 22)
        for stem in ALL_WINDOWS_DEVICE_STEMS:
            variants = (
                stem.upper(),
                stem.lower(),
                stem.capitalize(),
                f"{stem.lower()}.toml",
                f"{stem.upper()}.json",
                f"{stem.capitalize()}.v1.tar.gz",
                f"{stem.lower()} .toml",
                f"{stem.lower()}..json",
            )
            for candidate in variants:
                with self.subTest(candidate=candidate):
                    self.assertFalse(is_portable_name(candidate))
                    with self.assertRaises(portable_names.PortableNameError) as ctx:
                        portable_names.check_segment(candidate)
                    self.assertEqual(ctx.exception.segment, candidate)
                    self.assertIn("device name", ctx.exception.problem)

    def test_reserved_device_names_rejected_in_nested_paths(self) -> None:
        nested_cases = (
            ("xdr/cap-0083/con.toml", "con.toml"),
            ("xdr/nul.json", "nul.json"),
            ("soroban/aux/fixture-01.toml", "aux"),
            ("rpc/COM1/get-health.toml", "COM1"),
            ("ledger/lpt9.schema.json", "lpt9.schema.json"),
        )
        for rel_path, bad_segment in nested_cases:
            with self.subTest(path=rel_path):
                with self.assertRaises(portable_names.PortableNameError) as ctx:
                    portable_names.check_path(rel_path)
                self.assertEqual(ctx.exception.segment, bad_segment)

    def test_non_reserved_near_miss_device_stems_are_accepted(self) -> None:
        valid_near_misses = (
            "con0.toml",
            "console.toml",
            "aux-data.json",
            "nullable.toml",
            "com0.toml",
            "com10.toml",
            "lpt0.toml",
            "lpt10.toml",
            "prn-output.toml",
        )
        for name in valid_near_misses:
            with self.subTest(name=name):
                portable_names.check_segment(name)
                self.assertTrue(is_portable_name(name))


class TrailingDotAndWhitespaceTests(unittest.TestCase):
    """Rejection of trailing dots, trailing spaces, and empty path segments."""

    def test_trailing_periods_and_spaces_are_rejected(self) -> None:
        invalid_Names = (
            "fixture.",
            "fixture..",
            "fixture.toml.",
            "fixture ",
            "fixture   ",
            "fixture.toml ",
            "fixture .",
            "fixture. ",
            ".",
            "..",
            " ",
        )
        for segment in invalid_Names:
            with self.subTest(segment=segment):
                with self.assertRaises(portable_names.PortableNameError) as ctx:
                    portable_names.check_segment(segment)
                self.assertIn("ends in a dot or a space", ctx.exception.problem)

    def test_trailing_period_or_space_on_directory_component_is_rejected(self) -> None:
        for bad_dir in ("cap-0083.", "cap-0083 ", "fixtures.."):
            path = f"xdr/{bad_dir}/valid-case.toml"
            with self.subTest(path=path):
                with self.assertRaises(portable_names.PortableNameError) as ctx:
                    portable_names.check_path(path)
                self.assertEqual(ctx.exception.segment, bad_dir)

    def test_empty_segment_and_double_slashes_are_rejected(self) -> None:
        with self.assertRaises(portable_names.PortableNameError) as ctx:
            portable_names.check_segment("")
        self.assertEqual(ctx.exception.problem, "is empty")

        for bad_path in ("/xdr/case.toml", "xdr//case.toml", "xdr/case.toml/"):
            with self.subTest(path=bad_path):
                with self.assertRaises(portable_names.PortableNameError):
                    portable_names.check_path(bad_path)


class ForbiddenAndControlCharacterTests(unittest.TestCase):
    """Rejection of Windows forbidden characters and ASCII 0x00-0x1F control codes."""

    def test_all_windows_forbidden_characters_trigger_portable_name_error(self) -> None:
        for ch in FORBIDDEN_WINDOWS_CHARS:
            for sample in (f"bad{ch}name.toml", f"{ch}prefix.toml", f"suffix{ch}"):
                with self.subTest(char=ch, sample=sample):
                    with self.assertRaises(portable_names.PortableNameError) as ctx:
                        portable_names.check_segment(sample)
                    self.assertIn(repr(ch), ctx.exception.problem)

    def test_ascii_control_characters_0x00_to_0x1f_rejected_in_filenames_and_dirs(self) -> None:
        for code in range(0x00, 0x20):
            ctrl = chr(code)
            file_path = f"xdr/cap-0083/vector-{ctrl}-01.toml"
            dir_path = f"xdr/cap-{ctrl}-0083/vector-01.toml"
            with self.subTest(code=code, target="file"):
                with self.assertRaises(generate.PackError) as file_ctx:
                    validate_portable_names(file_path)
                self.assertIn("control character", str(file_ctx.exception))
            with self.subTest(code=code, target="dir"):
                with self.assertRaises(generate.PackError) as dir_ctx:
                    validate_portable_names(dir_path)
                self.assertIn("control character", str(dir_ctx.exception))


class ValidCrossPlatformNamesTests(unittest.TestCase):
    """Valid kebab-case alphanumeric names with hyphens and periods pass cleanly."""

    def test_kebab_case_alphanumeric_segments_and_paths_pass_without_error(self) -> None:
        valid_paths = (
            "xdr/cap-0083/tx-envelope-v1.toml",
            "soroban/host-fns/ledger-footprint-001.json",
            "rpc/get-events/cursor.pagination.v2.toml",
            "evidence/2026-11-24/canary-report-p28.tar.gz",
            "fixtures/account_merge-01/payload.bin",
        )
        for path in valid_paths:
            with self.subTest(path=path):
                portable_names.check_path(path)
                validate_portable_names(path)
                for segment in path.split("/"):
                    self.assertTrue(is_portable_name(segment))


if __name__ == "__main__":
    unittest.main()
