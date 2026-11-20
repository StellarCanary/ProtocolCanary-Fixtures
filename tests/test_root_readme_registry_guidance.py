"""The root README points to generated inventory, not fixture counts (issue #490).

The Protocol 28 pack grows with ordinary fixture contributions, and the
canonical registry is generated from the pack rather than committed. The root
README therefore summarises the pack, links its documentation and names the
command that prints the generated registry. These tests protect that guidance
without asserting how many fixtures the pack holds, so adding a fixture never
requires a root README edit.

Run with: python3 -m unittest tests.test_root_readme_registry_guidance
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"

REGISTRY_COMMAND = "python3 tools/registry/generate.py protocol-28 --stdout"
PACK_DOC_LINKS = ("(protocol-28/README.md)", "(docs/protocol-28.md)")

# A number next to a fixture or surface word, such as "6 total", "4 xdr" or
# "93 fixtures": the shape of a static count, whatever its value. A protocol
# version ("Protocol 28 RPC identity") is a name, not a count.
_COUNT_PATTERN = re.compile(
    r"(?<![Pp]rotocol )\b\d+\s+(?:fixtures?|xdr|rpc|soroban|total)\b", re.IGNORECASE
)


def protocol_28_row(text: str) -> str:
    """Return the Protocol packs table row for ``protocol-28/``."""
    rows = [line for line in text.splitlines() if line.startswith("| [`protocol-28/`]")]
    if len(rows) != 1:
        raise AssertionError(f"expected one protocol-28 pack row, found {len(rows)}")
    return rows[0]


def static_counts(text: str) -> list[str]:
    """Return every static fixture-count phrase in ``text``."""
    return [match.group(0) for match in _COUNT_PATTERN.finditer(text)]


class RootReadmeRegistryGuidanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = protocol_28_row(README_PATH.read_text(encoding="utf-8"))

    def test_protocol_28_row_states_no_static_fixture_counts(self) -> None:
        self.assertEqual(static_counts(self.row), [])

    def test_protocol_28_row_links_the_pack_documentation(self) -> None:
        for link in PACK_DOC_LINKS:
            with self.subTest(link=link):
                self.assertIn(link, self.row)
        for target in ("protocol-28/README.md", "docs/protocol-28.md"):
            with self.subTest(target=target):
                self.assertTrue((REPO_ROOT / target).is_file())

    def test_protocol_28_row_names_the_generated_registry_command(self) -> None:
        self.assertIn(f"`{REGISTRY_COMMAND}`", self.row)
        self.assertTrue((REPO_ROOT / "tools" / "registry" / "generate.py").is_file())


class GuidanceHelperTests(unittest.TestCase):
    def test_static_counts_finds_count_phrases(self) -> None:
        text = "Counts: **4 xdr, 1 rpc, 1 soroban** (6 total); 93 fixtures; 1 fixture"
        self.assertEqual(
            static_counts(text),
            ["4 xdr", "1 rpc", "1 soroban", "6 total", "93 fixtures", "1 fixture"],
        )

    def test_static_counts_ignores_protocol_and_cap_numbers(self) -> None:
        text = "Protocol 28 RPC identity; CAP-0083, CAP-0085 (XDR); protocol-28/"
        self.assertEqual(static_counts(text), [])

    def test_protocol_28_row_requires_exactly_one_row(self) -> None:
        with self.assertRaises(AssertionError):
            protocol_28_row("| [`protocol-29/`](protocol-29/) | Published | x |\n")


if __name__ == "__main__":
    unittest.main()
