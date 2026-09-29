"""Tests for tools/validate/validate.py.

Run with: python3 -m unittest discover tests
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_PATH = REPO_ROOT / "tools" / "validate" / "validate.py"

_spec = importlib.util.spec_from_file_location("validate", VALIDATE_PATH)
validate = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["validate"] = validate
_spec.loader.exec_module(validate)


VALID_XDR = """
id = "p28-xdr-cap83-example"
protocol = 28
surface = "xdr"
category = "cap-0083"
description = "example"
source_reference = "CAP-0083"

type = "StellarValue"
kind = "decode-success"
value_base64 = "AAAAAA=="
"""

VALID_RPC = """
id = "p28-rpc-example"
protocol = 28
surface = "rpc"
category = "network"
description = "example"
source_reference = "https://developers.stellar.org/docs/data/apis/rpc/api-reference/methods/getNetwork"

method = "get-network"

[[assert]]
kind = "field-equals"
field = "protocolVersion"
value = 28
"""

VALID_SOROBAN = """
id = "p28-soroban-example"
protocol = 28
surface = "soroban"
category = "smoke"
description = "example"
source_reference = "https://developers.stellar.org/docs/tokens/stellar-asset-contract"

source_account = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
contract_id = "CDLZFC3SYJYDZT7K67VZ75HPJVIEUVNIXF47ZG2FB2RMQQVU2HHGCYSC"
function = "name"
sequence_number = 1

[expect]
kind = "simulation-success"
"""


def write(dir_path: Path, name: str, contents: str) -> Path:
    path = dir_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


class ValidatorTests(unittest.TestCase):
    def run_validation(self, files: dict[str, str]) -> "validate.Report":
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, contents in files.items():
                write(root, name, contents)
            return validate.validate_directory(root)

    def test_accepts_a_valid_xdr_fixture(self) -> None:
        report = self.run_validation({"a.toml": VALID_XDR})
        self.assertEqual(report.errors, [])

    def test_accepts_a_valid_rpc_fixture(self) -> None:
        report = self.run_validation({"a.toml": VALID_RPC})
        self.assertEqual(report.errors, [])

    def test_accepts_a_valid_soroban_fixture(self) -> None:
        report = self.run_validation({"a.toml": VALID_SOROBAN})
        self.assertEqual(report.errors, [])

    def test_rejects_duplicate_ids(self) -> None:
        other = VALID_XDR.replace(
            'category = "cap-0083"', 'category = "cap-0083-2"'
        )
        report = self.run_validation({"a.toml": VALID_XDR, "b.toml": other})
        self.assertTrue(any("duplicate fixture id" in e for e in report.errors))

    # os.chmod() does not restrict access on Windows, and root ignores the
    # permission bits entirely on POSIX, so on both the file stays readable and
    # this error path cannot be provoked.
    @unittest.skipIf(
        os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
        "os.chmod is not effective on this platform/user",
    )
    def test_unreadable_file_reports_a_read_error(self) -> None:
        """A fixture file that cannot be read yields a 'failed to read file' error.

        Covers the ``except OSError`` branch in ``validate.load_fixture()``.
        Every other test uses ``TemporaryDirectory()``, where files are always
        readable, so this error path would otherwise go untested.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write(root, "a.toml", VALID_XDR)
            try:
                os.chmod(path, 0o000)
                try:
                    path.read_text(encoding="utf-8")
                except OSError:
                    pass
                else:
                    self.skipTest("a 0o000 file is still readable here")

                report = validate.validate_directory(root)
            finally:
                # Restore permissions before the directory is removed, so
                # cleanup never depends on the filesystem tolerating 0o000.
                os.chmod(path, 0o644)

        self.assertFalse(report.ok)
        matching = [e for e in report.errors if "failed to read file" in e]
        self.assertTrue(matching, f"expected a read error, got: {report.errors}")
        self.assertIn("a.toml", matching[0])

    def test_rejects_invalid_surface(self) -> None:
        bad = VALID_XDR.replace('surface = "xdr"', 'surface = "wallet"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("'surface'" in e for e in report.errors))

    def test_rejects_invalid_protocol_type(self) -> None:
        bad = VALID_XDR.replace("protocol = 28", 'protocol = "28"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("'protocol'" in e for e in report.errors))

    def test_rejects_missing_input_file(self) -> None:
        bad = VALID_XDR + '\ninput_file = "does-not-exist.xdr.b64"\n'
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("does not resolve to an existing file" in e for e in report.errors))

    def test_accepts_an_existing_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root, "input.xdr.b64", "AAAAAA==")
            write(root, "a.toml", VALID_XDR + '\ninput_file = "input.xdr.b64"\n')
            report = validate.validate_directory(root)
        self.assertEqual(report.errors, [])

    def test_rejects_invalid_expectation_kind(self) -> None:
        bad = VALID_XDR.replace('kind = "decode-success"', 'kind = "not-a-real-kind"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("'kind'" in e for e in report.errors))

    def test_encode_equals_requires_expected_base64(self) -> None:
        bad = VALID_XDR.replace('kind = "decode-success"', 'kind = "encode-equals"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("expected_base64" in e for e in report.errors))

    def test_rejects_empty_source_reference(self) -> None:
        bad = VALID_XDR.replace('source_reference = "CAP-0083"', 'source_reference = ""')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("source_reference" in e for e in report.errors))

    def test_warns_on_missing_source_reference(self) -> None:
        bad = VALID_XDR.replace('source_reference = "CAP-0083"\n', "")
        report = self.run_validation({"a.toml": bad})
        self.assertEqual(report.errors, [])
        self.assertTrue(any("source_reference" in w for w in report.warnings))

    def test_rejects_malformed_toml(self) -> None:
        report = self.run_validation({"a.toml": "not valid [[[ toml"})
        self.assertTrue(any("invalid TOML" in e for e in report.errors))

    def test_rejects_vague_category(self) -> None:
        bad = VALID_XDR.replace('category = "cap-0083"', 'category = "misc"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("too vague" in e for e in report.errors))

    def test_rejects_uppercase_id(self) -> None:
        bad = VALID_XDR.replace(
            'id = "p28-xdr-cap83-example"', 'id = "P28-XDR-CAP83-EXAMPLE"'
        )
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("lowercase" in e for e in report.errors))

    def test_rpc_fixture_requires_at_least_one_assert(self) -> None:
        bad = """
id = "p28-rpc-no-assert"
protocol = 28
surface = "rpc"
category = "network"
description = "example"
source_reference = "https://developers.stellar.org/docs/data/apis/rpc/api-reference/methods/getNetwork"

method = "get-network"
"""
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("at least one" in e for e in report.errors))

    def test_soroban_fixture_requires_expect(self) -> None:
        bad = VALID_SOROBAN.replace("[expect]\nkind = \"simulation-success\"\n", "")
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("'expect'" in e for e in report.errors))

    def test_rejects_invalid_base64_in_value_base64(self) -> None:
        bad = VALID_XDR.replace('value_base64 = "AAAAAA=="', 'value_base64 = "not-valid-base64!!!"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("not valid base64" in e and "value_base64" in e for e in report.errors))

    def test_rejects_malformed_padding_base64(self) -> None:
        bad = VALID_XDR.replace('value_base64 = "AAAAAA=="', 'value_base64 = "AAAAA"')
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("not valid base64" in e and "value_base64" in e for e in report.errors))

    def test_rejects_invalid_base64_in_expected_base64(self) -> None:
        bad = (
            VALID_XDR.replace('kind = "decode-success"', 'kind = "encode-equals"')
            + 'expected_base64 = "not-valid-base64!!!"\n'
        )
        report = self.run_validation({"a.toml": bad})
        self.assertTrue(any("not valid base64" in e and "expected_base64" in e for e in report.errors))

    def test_accepts_valid_base64_in_encode_equals(self) -> None:
        good = (
            VALID_XDR.replace('kind = "decode-success"', 'kind = "encode-equals"')
            + 'expected_base64 = "AAAAAA=="\n'
        )
        report = self.run_validation({"a.toml": good})
        self.assertEqual(report.errors, [])


if __name__ == "__main__":
    unittest.main()
