"""Tests for tools/pack/pack.py (F-018, CF-06 section 2).

Stdlib only: the CI `validate` job runs `unittest discover` on a bare
interpreter.

Run with: python3 -m unittest discover tests
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_support as support  # noqa: E402

pack = support.pack
REPO_ROOT = support.REPO_ROOT


class Scratch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def build(self, name: str = "out", version: str = "1.0.0") -> pack.ArchiveInfo:
        pack_dir = self.root / "pack"
        if not pack_dir.exists():
            support.write_pack(self.root)
        return pack.build_archive(pack_dir, self.root / name, version)

    def members(self, archive: Path) -> list[tarfile.TarInfo]:
        with tarfile.open(archive, "r:gz") as handle:
            return handle.getmembers()


class ReproducibilityTests(Scratch):
    def test_two_builds_have_identical_bytes_and_hash(self) -> None:
        first = self.build("one")
        second = self.build("two")
        self.assertEqual(first.path.read_bytes(), second.path.read_bytes())
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.sha256, hashlib.sha256(first.path.read_bytes()).hexdigest())

    def test_build_does_not_depend_on_location_or_mtime(self) -> None:
        first = self.build("one")
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(elsewhere, ignore_errors=True))
        other_pack = support.write_pack(elsewhere)
        for path in other_pack.rglob("*"):
            os.utime(path, (1_000_000_000, 1_000_000_000))
        second = pack.build_archive(other_pack, elsewhere / "out", "1.0.0")
        self.assertEqual(first.sha256, second.sha256)

    def test_gzip_header_has_no_name_and_no_timestamp(self) -> None:
        data = self.build().path.read_bytes()
        self.assertEqual(data[:2], b"\x1f\x8b")
        self.assertEqual(data[3], 0, "FLG must be 0: no FNAME, FEXTRA or FCOMMENT")
        self.assertEqual(data[4:8], b"\x00\x00\x00\x00", "MTIME must be 0")

    def test_one_changed_byte_changes_the_archive(self) -> None:
        first = self.build("one")
        (self.root / "pack" / "xdr" / "a.bin").write_bytes(b"\x00\x01payload\xfe\n")
        second = self.build("two")
        self.assertNotEqual(first.sha256, second.sha256)


class EntryNormalisationTests(Scratch):
    def test_entries_are_sorted_in_byte_order_with_directories_first(self) -> None:
        names = [m.name for m in self.members(self.build().path)]
        self.assertEqual(
            names,
            ["registry.json", "rpc", "rpc/b.toml", "xdr", "xdr/a.bin", "xdr/a.toml"],
        )
        self.assertEqual(names, sorted(names, key=lambda n: n.encode("utf-8")))

    def test_owner_time_and_mode_are_normalised(self) -> None:
        for member in self.members(self.build().path):
            with self.subTest(member.name):
                self.assertEqual((member.uid, member.gid), (0, 0))
                self.assertEqual((member.uname, member.gname), ("", ""))
                self.assertEqual(member.mtime, 0)
                self.assertEqual(member.mode, 0o755 if member.isdir() else 0o644)
                self.assertTrue(member.isdir() or member.isreg())

    def test_source_file_modes_do_not_leak_into_the_archive(self) -> None:
        pack_dir = support.write_pack(self.root)
        if os.name == "posix":
            os.chmod(pack_dir / "xdr" / "a.toml", 0o777)
        info = pack.build_archive(pack_dir, self.root / "out", "1.0.0")
        modes = {m.mode for m in self.members(info.path) if m.isreg()}
        self.assertEqual(modes, {0o644})

    def test_archive_holds_the_pack_membership_plus_the_registry_only(self) -> None:
        pack_dir = support.write_pack(self.root)
        (pack_dir / "README.md").write_text("not part of the pack")
        (pack_dir / "xdr" / "notes.txt").write_text("unreferenced")
        info = pack.build_archive(pack_dir, self.root / "out", "1.0.0")
        files = sorted(m.name for m in self.members(info.path) if m.isreg())
        self.assertEqual(files, ["registry.json", "rpc/b.toml", "xdr/a.bin", "xdr/a.toml"])

    def test_registry_in_the_archive_is_the_generated_one(self) -> None:
        info = self.build()
        with tarfile.open(info.path, "r:gz") as handle:
            stored = handle.extractfile("registry.json").read()
        expected = pack.generate.generate(self.root / "pack").encode("utf-8")
        self.assertEqual(stored, expected)

    def test_info_matches_the_archive(self) -> None:
        info = self.build()
        members = self.members(info.path)
        self.assertEqual(info.entries, len(members))
        self.assertEqual(info.uncompressed_bytes, sum(m.size for m in members if m.isreg()))
        self.assertEqual(info.size, info.path.stat().st_size)
        self.assertEqual(info.pack_digest, support.GOLDEN_DIGEST)
        self.assertEqual(info.protocol, 28)


class RoundTripTests(Scratch):
    def test_unpacked_files_hash_to_the_pack_digest(self) -> None:
        info = self.build()
        files = {}
        with tarfile.open(info.path, "r:gz") as handle:
            for member in handle:
                if member.isreg() and member.name != "registry.json":
                    files[member.name] = handle.extractfile(member).read()
        lines = ["canary-pack-v1\n"]
        for path in sorted(files, key=lambda p: p.encode("utf-8")):
            lines.append(f"{hashlib.sha256(files[path]).hexdigest()} {len(files[path])} {path}\n")
        digest = "sha256:" + hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
        self.assertEqual(digest, info.pack_digest)
        self.assertEqual(digest, support.GOLDEN_DIGEST)

    def test_the_real_protocol_28_pack_builds_and_verifies(self) -> None:
        pack_dir = REPO_ROOT / "protocol-28"
        info = pack.build_archive(pack_dir, self.root / "out", "1.2.3")
        self.assertEqual(info.path.name, "protocolcanary-fixtures-1.2.3.tar.gz")
        again = pack.build_archive(pack_dir, self.root / "again", "1.2.3")
        self.assertEqual(info.sha256, again.sha256)
        self.assertGreater(info.entries, 1)


class LimitTests(Scratch):
    def test_too_many_entries_are_refused(self) -> None:
        members = {f"f{i:04d}.toml": b"" for i in range(pack.MAX_ENTRIES + 1)}
        with self.assertRaisesRegex(pack.PackError, "entries"):
            pack.render_archive(members)

    def test_exactly_the_entry_limit_is_accepted(self) -> None:
        members = {f"f{i:04d}.toml": b"" for i in range(pack.MAX_ENTRIES)}
        self.assertTrue(pack.render_archive(members))

    def test_directories_count_as_entries(self) -> None:
        members = {f"d{i:04d}/f.toml": b"" for i in range(pack.MAX_ENTRIES // 2 + 1)}
        with self.assertRaisesRegex(pack.PackError, "entries"):
            pack.render_archive(members)

    def test_oversize_file_is_refused(self) -> None:
        members = {"big.toml": b"#" * (pack.MAX_FILE_BYTES + 1)}
        with self.assertRaisesRegex(pack.PackError, "limit for one file"):
            pack.render_archive(members)

    def test_total_size_is_refused(self) -> None:
        count = pack.MAX_TOTAL_BYTES // pack.MAX_FILE_BYTES + 1
        members = {f"f{i}.toml": b"#" * pack.MAX_FILE_BYTES for i in range(count)}
        with self.assertRaisesRegex(pack.PackError, "uncompressed"):
            pack.render_archive(members)

    def test_depth_limit(self) -> None:
        deep = "/".join(["d"] * pack.MAX_DEPTH) + "/f.toml"
        with self.assertRaisesRegex(pack.PackError, "deeper"):
            pack.render_archive({deep: b""})
        ok = "/".join(["d"] * (pack.MAX_DEPTH - 1)) + "/f.toml"
        self.assertTrue(pack.render_archive({ok: b""}))


class InvalidInputTests(Scratch):
    def test_missing_pack_directory_is_a_pack_error(self) -> None:
        with self.assertRaisesRegex(pack.PackError, "not a directory"):
            pack.build_archive(self.root / "absent", self.root / "out", "1.0.0")
        self.assertFalse((self.root / "out").exists())

    def test_empty_pack_is_refused(self) -> None:
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(pack.PackError, "no \\*.toml"):
            pack.build_archive(self.root / "empty", self.root / "out", "1.0.0")

    def test_bad_version_names_the_expected_form(self) -> None:
        support.write_pack(self.root)
        for bad in ["1.0", "v1.0.0", "1.0.0-rc1", "01.0.0", ""]:
            with self.subTest(bad):
                with self.assertRaisesRegex(pack.PackError, "MAJOR.MINOR.PATCH"):
                    pack.build_archive(self.root / "pack", self.root / "out", bad)

    def test_missing_payload_is_refused_and_nothing_is_written(self) -> None:
        pack_dir = support.write_pack(self.root)
        (pack_dir / "xdr" / "a.bin").unlink()
        with self.assertRaisesRegex(pack.PackError, "does not exist"):
            pack.build_archive(pack_dir, self.root / "out", "1.0.0")
        self.assertFalse((self.root / "out").exists())

    def test_two_protocols_in_one_pack_are_refused(self) -> None:
        pack_dir = support.write_pack(self.root)
        other = support.B_TOML.replace(b"protocol = 28", b"protocol = 29").replace(
            b"p28-rpc-b", b"p29-rpc-b"
        )
        (pack_dir / "rpc" / "c.toml").write_bytes(other)
        with self.assertRaisesRegex(pack.PackError, "exactly one protocol"):
            pack.build_archive(pack_dir, self.root / "out", "1.0.0")

    @unittest.skipUnless(hasattr(os, "symlink") and os.name == "posix", "needs POSIX symlinks")
    def test_symlink_in_the_pack_is_refused(self) -> None:
        pack_dir = support.write_pack(self.root)
        os.symlink(pack_dir / "xdr" / "a.bin", pack_dir / "xdr" / "link.bin")
        with self.assertRaisesRegex(pack.PackError, "symbolic link"):
            pack.build_archive(pack_dir, self.root / "out", "1.0.0")

    def test_cli_reports_failure_with_exit_code_1(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = pack.main(["absent-pack-dir", "--version", "1.0.0", "--output-dir", str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("FAILED: no archive written", err.getvalue())

    def test_cli_success_prints_the_hash(self) -> None:
        support.write_pack(self.root)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pack.main(
                [str(self.root / "pack"), "--version", "2.0.0", "--output-dir", str(self.root / "o")]
            )
        self.assertEqual(code, 0)
        archive = self.root / "o" / "protocolcanary-fixtures-2.0.0.tar.gz"
        self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(), out.getvalue())


class ReadAndWriteFailureTests(Scratch):
    """The OSError branches around reading the pack and writing the archive."""

    @unittest.skipUnless(os.name == "posix", "needs POSIX file permissions")
    def test_an_unreadable_pack_file_is_a_pack_error(self) -> None:
        pack_dir = support.write_pack(self.root)
        victim = pack_dir / "xdr" / "a.toml"
        os.chmod(victim, 0o000)
        self.addCleanup(os.chmod, victim, 0o644)
        with self.assertRaisesRegex(pack.PackError, "could not read the pack"):
            pack.collect_members(pack_dir)

    def test_an_unwritable_output_directory_is_reported_by_the_cli(self) -> None:
        support.write_pack(self.root)
        blocker = self.root / "blocker"
        blocker.write_bytes(b"i am a file, not a directory")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = pack.main(
                [
                    str(self.root / "pack"),
                    "--version",
                    "1.0.0",
                    "--output-dir",
                    str(blocker / "nested"),
                ]
            )
        self.assertEqual(code, 1)
        self.assertIn("could not write the archive", err.getvalue())

    def test_module_entry_point_exits_zero_on_success(self) -> None:
        support.write_pack(self.root)
        run = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "pack" / "pack.py"),
                str(self.root / "pack"),
                "--version",
                "3.1.4",
                "--output-dir",
                str(self.root / "dist"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=self.root,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("OK: wrote", run.stdout)
        self.assertTrue(
            (self.root / "dist" / "protocolcanary-fixtures-3.1.4.tar.gz").is_file()
        )

    def test_module_entry_point_exits_one_on_failure(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "pack" / "pack.py"),
                str(self.root / "absent"),
                "--version",
                "1.0.0",
                "--output-dir",
                str(self.root / "dist"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=self.root,
        )
        self.assertEqual(run.returncode, 1)
        self.assertIn("FAILED: no archive written", run.stderr)

    def test_module_main_guard_runs_in_process(self) -> None:
        import runpy

        support.write_pack(self.root)
        argv = sys.argv
        sys.argv = [
            "pack.py",
            str(self.root / "pack"),
            "--version",
            "1.0.0",
            "--output-dir",
            str(self.root / "dist"),
        ]
        self.addCleanup(setattr, sys, "argv", argv)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_path(
                    str(REPO_ROOT / "tools" / "pack" / "pack.py"), run_name="__main__"
                )
        self.assertEqual(caught.exception.code, 0)
        self.assertTrue(
            (self.root / "dist" / "protocolcanary-fixtures-1.0.0.tar.gz").is_file()
        )


class VerifiedPackTests(Scratch):
    def write_evidence(self, *, outcome: str = "matched", bad_hash: bool = False) -> None:
        pack_dir = self.root / "pack"
        scanned = pack.generate.scan_pack(pack_dir)
        registry = pack.generate.build_registry(scanned)
        records = pack_dir / "evidence" / "records"
        records.mkdir(parents=True)
        for fixture in registry["fixtures"]:
            digest = hashlib.sha256(scanned[fixture["path"]]).hexdigest()
            if bad_hash:
                digest = "0" * 64
            record = {
                "verificationVersion": 1,
                "fixtureId": fixture["id"],
                "fixtureSha256": digest,
                "method": "structural",
                "checkedAt": datetime.datetime.now(datetime.UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "verifier": {"name": "test", "version": "1"},
                "outcome": outcome,
            }
            (records / f"{fixture['id']}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )

    def run_verified(self) -> int:
        return pack.main(
            [
                str(self.root / "pack"),
                "--version",
                "1.0.0",
                "--output-dir",
                str(self.root / "dist"),
                "--verified",
            ]
        )

    def setUp(self) -> None:
        super().setUp()
        support.write_pack(self.root)

    def test_verified_pack_requires_evidence(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_verified(), 1)
        self.assertFalse((self.root / "dist").exists())

    def test_verified_pack_accepts_matching_passing_evidence(self) -> None:
        self.write_evidence()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.run_verified(), 0)
        self.assertTrue((self.root / "dist" / "protocolcanary-fixtures-1.0.0.tar.gz").is_file())

    def test_verified_pack_rejects_mismatched_hashes_and_failed_outcomes(self) -> None:
        for bad_hash, outcome in ((True, "matched"), (False, "mismatched")):
            with self.subTest(bad_hash=bad_hash, outcome=outcome):
                evidence = self.root / "pack" / "evidence"
                if evidence.exists():
                    __import__("shutil").rmtree(evidence)
                self.write_evidence(bad_hash=bad_hash, outcome=outcome)
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(self.run_verified(), 1)

    def test_verified_pack_rejects_zero_fixtures(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(pack.PackError, "zero fixtures"):
            pack.check_verified_evidence(empty)

    def write_protocol29_live_evidence(self, pack_dir: Path) -> None:
        import datetime

        fixture_dir = pack_dir / "rpc"
        fixture_dir.mkdir(parents=True)
        fixture_id = "p29-rpc-version-info-protocol-29"
        fixture = (
            f'id = "{fixture_id}"\n'
            "protocol = 29\n"
            'surface = "rpc"\n'
            'category = "network"\n'
            'description = "version info identifies Protocol 29"\n'
            'source_reference = "https://developers.stellar.org/docs/data/apis/rpc/api-reference/methods/getVersionInfo"\n'
            'method = "get-version-info"\n\n'
            '[[assert]]\nkind = "field-equals"\nfield = "protocolVersion"\nvalue = 29\n'
        )
        fixture_path = fixture_dir / f"{fixture_id}.toml"
        fixture_path.write_text(fixture, encoding="utf-8")
        fixture_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        checked_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        networks = {
            "testnet": (
                "soroban-testnet.stellar.org",
                "Test SDF Network ; September 2015",
            ),
            "futurenet": (
                "rpc-futurenet.stellar.org",
                "Test SDF Future Network ; October 2022",
            ),
        }
        for network, (host, passphrase) in networks.items():
            capture_dir = pack_dir / "evidence" / "live" / network / "captures"
            record_dir = pack_dir / "evidence" / "live" / network / "records"
            capture_dir.mkdir(parents=True)
            record_dir.mkdir(parents=True)
            capture = {
                "capturedAt": checked_at,
                "endpointHost": host,
                "request": {"jsonrpc": "2.0", "id": 2, "method": "getVersionInfo"},
                "response": {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"protocolVersion": 29},
                },
            }
            (capture_dir / "get-version-info.json").write_text(
                json.dumps(capture), encoding="utf-8"
            )
            network_capture = {
                "capturedAt": checked_at,
                "endpointHost": host,
                "request": {"jsonrpc": "2.0", "id": 1, "method": "getNetwork"},
                "response": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {"passphrase": passphrase, "protocolVersion": 29},
                },
            }
            (capture_dir / "get-network.json").write_text(
                json.dumps(network_capture), encoding="utf-8"
            )
            record = {
                "verificationVersion": 1,
                "fixtureId": fixture_id,
                "fixtureSha256": fixture_hash,
                "method": "live-read-only",
                "checkedAt": checked_at,
                "verifier": {"name": "test", "version": "1"},
                "outcome": "matched",
                "network": {
                    "name": network,
                    "passphrase": passphrase,
                    "observedProtocol": 29,
                },
                "endpointHost": host,
                "evidenceRef": (
                    f"{pack_dir.name}/evidence/live/{network}/captures/get-version-info.json"
                ),
            }
            (record_dir / f"{fixture_id}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )

    def test_protocol29_verified_pack_requires_both_network_captures(self) -> None:
        pack_dir = self.root / "protocol-29"
        pack_dir.mkdir()
        self.write_protocol29_live_evidence(pack_dir)
        pack.check_verified_evidence(pack_dir)

        futurenet_records = pack_dir / "evidence" / "live" / "futurenet" / "records"
        __import__("shutil").rmtree(futurenet_records)
        with self.assertRaisesRegex(pack.PackError, "Testnet and Futurenet"):
            pack.check_verified_evidence(pack_dir)

    def test_protocol29_verified_pack_rejects_stale_live_records(self) -> None:
        pack_dir = self.root / "protocol-29"
        pack_dir.mkdir()
        self.write_protocol29_live_evidence(pack_dir)
        for record_path in (pack_dir / "evidence" / "live").rglob("records/*.json"):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["checkedAt"] = "2020-01-01T00:00:00Z"
            record_path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(pack.PackError, "30-day freshness"):
            pack.check_verified_evidence(pack_dir)


class CompressionFormatTests(Scratch):
    """Issue #598: pack validation rejects archives with wrong compression.

    A ProtocolCanary fixture archive is always a gzip-compressed tar (CF-06).
    ``verify_archive.extract_safely`` opens archives with ``mode="r|gz"``, so
    a plain (uncompressed) tar stream, a corrupt gzip header, or a bare gzip
    file that wraps non-tar data are all *unreadable* rather than merely
    *invalid*: the tool raises ``UnreadableArchive`` before it can inspect any
    entry.  Every test here cleans up its temporary archive via the ``Scratch``
    base class.
    """

    def _make_plain_tar(self, name: str = "plain.tar") -> Path:
        """Write a valid fixture pack as a plain (non-gzip) tar archive."""
        pack_dir = support.write_pack(self.root)
        members, _, _ = pack.collect_members(pack_dir)
        archive = self.root / name
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:", format=tarfile.PAX_FORMAT) as tf:
            for entry_name, data in sorted(members.items()):
                info = tarfile.TarInfo(entry_name)
                info.size = len(data)
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
        archive.write_bytes(raw.getvalue())
        return archive

    def test_uncompressed_tar_is_unreadable_by_the_safe_extractor(self) -> None:
        archive = self._make_plain_tar()
        dest = self.root / "dest"
        dest.mkdir()
        with self.assertRaises(support.verify_archive.UnreadableArchive) as caught:
            support.verify_archive.extract_safely(archive, dest)
        self.assertIn("cannot read the archive", str(caught.exception))

    def test_uncompressed_tar_is_rejected_by_verify_archive(self) -> None:
        archive = self._make_plain_tar()
        with self.assertRaises(support.verify_archive.UnreadableArchive) as caught:
            support.verify_archive.verify_archive(archive)
        self.assertIn("cannot read the archive", str(caught.exception))

    def test_uncompressed_tar_exit_code_is_2_via_cli(self) -> None:
        # The CLI documents exit code 2 for an unusable (unreadable) archive.
        archive = self._make_plain_tar()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = support.verify_archive.main([str(archive)])
        self.assertEqual(code, 2)
        self.assertIn("error:", err.getvalue())

    def test_bare_gzip_wrapping_non_tar_data_is_unreadable(self) -> None:
        # A gzip stream that does not contain a valid tar is also rejected.
        import gzip as _gzip

        archive = self.root / "not_a_tar.tar.gz"
        raw = io.BytesIO()
        with _gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(b"this is not a tar archive at all\n" * 10)
        archive.write_bytes(raw.getvalue())

        dest = self.root / "dest2"
        dest.mkdir()
        with self.assertRaises(support.verify_archive.UnreadableArchive) as caught:
            support.verify_archive.extract_safely(archive, dest)
        self.assertIn("cannot read the archive", str(caught.exception))

    def test_truncated_gzip_archive_is_rejected_with_format_error(self) -> None:
        # A gzip file truncated mid-stream cannot be decoded.
        info = self.build()
        truncated = self.root / "truncated.tar.gz"
        full = info.path.read_bytes()
        truncated.write_bytes(full[: len(full) // 2])

        dest = self.root / "dest3"
        dest.mkdir()
        with self.assertRaises(support.verify_archive.UnreadableArchive) as caught:
            support.verify_archive.extract_safely(truncated, dest)
        self.assertIn("cannot read the archive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
