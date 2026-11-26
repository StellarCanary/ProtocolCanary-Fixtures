"""Archive determinism tests for tools/pack/pack.py (issue #666).

Verifies member sorting, mtime normalization, permission/umask independence,
gzip header metadata, and SHA-256 digest & checksum verification across builds.

Stdlib only: the CI ``validate`` job runs ``unittest discover`` on a bare
interpreter.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(REPO_ROOT / "tests"))
import pack_support as support  # noqa: E402

pack = support.pack
manifest_tool = support.manifest


def _write_nested_pack(root: Path, *, reverse_creation: bool = False) -> Path:
    """Create a valid sample pack with nested directories in controlled order."""
    pack_dir = root / "pack"
    specs = [
        ("alpha/a-first.toml", _xdr_toml("p28-xdr-alpha-first", "alpha.bin")),
        ("alpha/alpha.bin", b"\x00\x01alpha\n"),
        ("alpha/nested/b-second.toml", _xdr_toml("p28-xdr-alpha-second")),
        ("rpc/01-network.toml", _rpc_toml("p28-rpc-01-network")),
        ("zeta/z-last.toml", _xdr_toml("p28-xdr-zeta-last")),
    ]
    if reverse_creation:
        specs = list(reversed(specs))
    for rel, content in specs:
        target = pack_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return pack_dir


def _xdr_toml(fixture_id: str, input_file: str | None = None) -> bytes:
    lines = [
        f'id = "{fixture_id}"',
        "protocol = 28",
        'surface = "xdr"',
        'category = "cap-0083"',
        f'description = "determinism fixture {fixture_id}"',
        'source_reference = "CAP-0083"',
    ]
    if input_file is not None:
        lines.append(f'input_file = "{input_file}"')
    lines.extend(
        [
            'type = "StellarValue"',
            'kind = "decode-success"',
            'value_base64 = "AAAAAA=="',
        ]
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _rpc_toml(fixture_id: str) -> bytes:
    return (
        f'id = "{fixture_id}"\n'
        "protocol = 28\n"
        'surface = "rpc"\n'
        'category = "network"\n'
        f'description = "determinism fixture {fixture_id}"\n'
        'source_reference = "https://developers.stellar.org/docs/data/apis/rpc/api-reference/methods/getNetwork"\n'
        'method = "get-network"\n\n'
        "[[assert]]\n"
        'kind = "field-exists"\n'
        'field = "passphrase"\n'
    ).encode()


class PackArchiveDeterminismTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="pack-determinism-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _tar_members(self, archive_path: Path) -> list[tarfile.TarInfo]:
        with tarfile.open(archive_path, "r:gz") as archive:
            return archive.getmembers()

    def test_altered_mtimes_yield_byte_identical_archives_and_digests(self) -> None:
        first_root = self.root / "run1"
        second_root = self.root / "run2"
        pack_one = _write_nested_pack(first_root)
        pack_two = _write_nested_pack(second_root)

        for idx, path in enumerate(sorted(pack_one.rglob("*"))):
            os.utime(path, (1_500_000_000 + idx * 17, 1_500_000_000 + idx * 17))
        for idx, path in enumerate(sorted(pack_two.rglob("*"))):
            os.utime(path, (1_900_000_000 - idx * 31, 1_900_000_000 - idx * 31))

        info_one = pack.build_archive(pack_one, self.root / "out1", "1.0.0")
        info_two = pack.build_archive(pack_two, self.root / "out2", "1.0.0")

        bytes_one = info_one.path.read_bytes()
        bytes_two = info_two.path.read_bytes()
        self.assertEqual(bytes_one, bytes_two)
        self.assertEqual(info_one.sha256, info_two.sha256)
        self.assertEqual(info_one.pack_digest, info_two.pack_digest)
        self.assertEqual(info_one.sha256, hashlib.sha256(bytes_one).hexdigest())

        for member in self._tar_members(info_one.path):
            with self.subTest(member=member.name):
                self.assertEqual(member.mtime, 0)

    def test_permissions_and_umask_are_normalized_in_tar_headers(self) -> None:
        original_umask = os.umask(0o022)
        self.addCleanup(os.umask, original_umask)

        os.umask(0o002)
        pack_permissive = _write_nested_pack(self.root / "permissive")
        if os.name == "posix":
            for path in pack_permissive.rglob("*"):
                os.chmod(path, 0o755 if path.is_dir() else 0o777)
        info_permissive = pack.build_archive(pack_permissive, self.root / "out_perm", "1.0.0")

        os.umask(0o077)
        pack_restrictive = _write_nested_pack(self.root / "restrictive")
        if os.name == "posix":
            for path in pack_restrictive.rglob("*"):
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
        info_restrictive = pack.build_archive(pack_restrictive, self.root / "out_rest", "1.0.0")

        self.assertEqual(info_permissive.path.read_bytes(), info_restrictive.path.read_bytes())
        self.assertEqual(info_permissive.sha256, info_restrictive.sha256)

        for member in self._tar_members(info_restrictive.path):
            with self.subTest(member=member.name):
                expected_mode = pack.DIRECTORY_MODE if member.isdir() else pack.FILE_MODE
                self.assertEqual(member.mode, expected_mode)
                self.assertEqual(member.uid, 0)
                self.assertEqual(member.gid, 0)
                self.assertEqual(member.uname, "")
                self.assertEqual(member.gname, "")
                self.assertEqual(member.mtime, 0)
                self.assertEqual(member.pax_headers, {})

    def test_tar_entries_are_sorted_lexicographically_regardless_of_traversal_order(self) -> None:
        pack_forward = _write_nested_pack(self.root / "forward", reverse_creation=False)
        pack_reverse = _write_nested_pack(self.root / "reverse", reverse_creation=True)

        info_forward = pack.build_archive(pack_forward, self.root / "out_fwd", "1.0.0")

        orig_scan = pack.generate.scan_pack

        def reversed_scan(pack_dir: Path) -> dict[str, bytes]:
            scanned = orig_scan(pack_dir)
            return dict(reversed(list(scanned.items())))

        with patch.object(pack.generate, "scan_pack", side_effect=reversed_scan):
            info_reverse = pack.build_archive(pack_reverse, self.root / "out_rev", "1.0.0")

        self.assertEqual(info_forward.path.read_bytes(), info_reverse.path.read_bytes())

        names = [member.name for member in self._tar_members(info_forward.path)]
        expected_order = [
            "alpha",
            "alpha/a-first.toml",
            "alpha/alpha.bin",
            "alpha/nested",
            "alpha/nested/b-second.toml",
            "registry.json",
            "rpc",
            "rpc/01-network.toml",
            "zeta",
            "zeta/z-last.toml",
        ]
        self.assertEqual(names, expected_order)
        self.assertEqual(names, sorted(names, key=lambda name: name.encode("utf-8")))

    def test_render_archive_sorts_utf8_paths_regardless_of_dict_insertion_order(self) -> None:
        ordered = {
            "a/1.toml": b"one",
            "b/sub/2.toml": b"two",
            "registry.json": b"{}",
            "z/9.toml": b"nine",
        }
        shuffled = {
            "z/9.toml": b"nine",
            "registry.json": b"{}",
            "b/sub/2.toml": b"two",
            "a/1.toml": b"one",
        }

        bytes_ordered = pack.render_archive(ordered)
        bytes_shuffled = pack.render_archive(shuffled)
        self.assertEqual(bytes_ordered, bytes_shuffled)

        with tarfile.open(fileobj=io.BytesIO(bytes_shuffled), mode="r:gz") as archive:
            names = [member.name for member in archive.getmembers()]
        self.assertEqual(
            names,
            ["a", "a/1.toml", "b", "b/sub", "b/sub/2.toml", "registry.json", "z", "z/9.toml"],
        )

    def test_generated_sha256_checksum_file_and_cli_output_match_archive_digest(self) -> None:
        pack_dir = _write_nested_pack(self.root / "checksum")
        dist_dir = self.root / "dist"

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = pack.main(
                [str(pack_dir), "--version", "2.3.4", "--output-dir", str(dist_dir)]
            )
        self.assertEqual(code, 0)

        archive_path = dist_dir / "protocolcanary-fixtures-2.3.4.tar.gz"
        expected_digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        self.assertIn(f"sha256   {expected_digest}", stdout.getvalue())

        sha256_path = dist_dir / "protocolcanary-fixtures-2.3.4.sha256"
        manifest_path = dist_dir / "protocolcanary-fixtures-2.3.4.manifest.json"
        with contextlib.redirect_stdout(io.StringIO()):
            manifest_code = manifest_tool.main(
                [
                    str(archive_path),
                    "--revision",
                    support.REVISION,
                    "--output",
                    str(manifest_path),
                    "--sha256-file",
                    str(sha256_path),
                ]
            )
        self.assertEqual(manifest_code, 0)

        checksum_line = sha256_path.read_text(encoding="utf-8")
        self.assertEqual(checksum_line, f"{expected_digest}  {archive_path.name}\n")
        recorded_digest, recorded_name = checksum_line.strip().split("  ")
        self.assertEqual(recorded_digest, expected_digest)
        self.assertEqual(recorded_name, archive_path.name)

        # Rebuilding the same pack into a fresh directory yields the exact same checksum file.
        copy_dir = self.root / "copy"
        shutil.copytree(pack_dir, copy_dir)
        info_again = pack.build_archive(copy_dir, self.root / "dist2", "2.3.4")
        self.assertEqual(info_again.sha256, recorded_digest)


if __name__ == "__main__":
    unittest.main()
