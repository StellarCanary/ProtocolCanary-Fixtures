"""Unit tests for independent pure-Python XDR codec (issue #348)."""
from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import xdr_codec


class XdrCodecUnitTests(unittest.TestCase):
    def test_stellar_value_basic_roundtrip(self) -> None:
        raw_b64 = "EREREREREREREREREREREREREREREREREREREREREREAAAAAaOd4AAAAAAAAAAAA"
        raw = base64.b64decode(raw_b64)
        val = xdr_codec.decode_stellar_value(raw)
        self.assertEqual(val.ext.ext_type, xdr_codec.STELLAR_VALUE_BASIC)
        re_encoded = xdr_codec.encode_stellar_value(val)
        self.assertEqual(raw, re_encoded)

    def test_stellar_value_signed_roundtrip(self) -> None:
        raw_b64 = "EREREREREREREREREREREREREREREREREREREREREREAAAAAaOd4AAAAAAAAAAABAAAAACIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiAAAAQDMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzM="
        raw = base64.b64decode(raw_b64)
        val = xdr_codec.decode_stellar_value(raw)
        self.assertEqual(val.ext.ext_type, xdr_codec.STELLAR_VALUE_SIGNED)
        re_encoded = xdr_codec.encode_stellar_value(val)
        self.assertEqual(raw, re_encoded)

    def test_stellar_value_empty_tx_set_roundtrip(self) -> None:
        raw_b64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAaIwDgAAAAAAAAAACEREREREREREREREREREREREREREREREREREREREREREiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIiIgAAABwAAAAAMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMAAABARERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERERA=="
        raw = base64.b64decode(raw_b64)
        val = xdr_codec.decode_stellar_value(raw)
        self.assertEqual(val.ext.ext_type, xdr_codec.STELLAR_VALUE_EMPTY_TX_SET)
        re_encoded = xdr_codec.encode_stellar_value(val)
        self.assertEqual(raw, re_encoded)

    def test_contract_executable_wasm_roundtrip(self) -> None:
        raw_b64 = "AAAAAKurq6urq6urq6urq6urq6urq6urq6urq6urq6urq6ur"
        raw = base64.b64decode(raw_b64)
        val = xdr_codec.decode_contract_executable(raw)
        self.assertEqual(val.executable_type, xdr_codec.CONTRACT_EXECUTABLE_WASM)
        re_encoded = xdr_codec.encode_contract_executable(val)
        self.assertEqual(raw, re_encoded)

    def test_contract_executable_stellar_asset_roundtrip(self) -> None:
        raw_b64 = "AAAAAQ=="
        raw = base64.b64decode(raw_b64)
        val = xdr_codec.decode_contract_executable(raw)
        self.assertEqual(val.executable_type, xdr_codec.CONTRACT_EXECUTABLE_STELLAR_ASSET)
        re_encoded = xdr_codec.encode_contract_executable(val)
        self.assertEqual(raw, re_encoded)

    def test_contract_executable_external_ref_roundtrip(self) -> None:
        raw_b64 = "AAAAAgAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVQAAAAhmbGVldC12MQ=="
        raw = base64.b64decode(raw_b64)
        val = xdr_codec.decode_contract_executable(raw)
        self.assertEqual(val.executable_type, xdr_codec.CONTRACT_EXECUTABLE_EXTERNAL_REF)
        self.assertEqual(val.external_ref.tag, "fleet-v1")
        re_encoded = xdr_codec.encode_contract_executable(val)
        self.assertEqual(raw, re_encoded)

    def test_truncation_at_every_byte_offset(self) -> None:
        # Test on both StellarValue and ContractExecutable
        fixtures = [
            ("StellarValue", base64.b64decode("EREREREREREREREREREREREREREREREREREREREREREAAAAAaOd4AAAAAAAAAAAA")),
            ("ContractExecutable", base64.b64decode("AAAAAgAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVQAAAAhmbGVldC12MQ==")),
        ]
        for type_name, full_bytes in fixtures:
            for length in range(len(full_bytes)):
                truncated = full_bytes[:length]
                with self.assertRaises(xdr_codec.XdrCodecError, msg=f"{type_name} cut at offset {length}"):
                    xdr_codec.decode_xdr(type_name, truncated)

    def test_trailing_bytes_rejected(self) -> None:
        raw = base64.b64decode("AAAAAQ==")  # ContractExecutable StellarAsset (4 bytes)
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_contract_executable(raw + b"\x00")

    def test_unknown_discriminants_rejected(self) -> None:
        # ContractExecutable discriminant 99
        bad_exec = (99).to_bytes(4, "big")
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_contract_executable(bad_exec)

        # StellarValue ext discriminant 99
        # 32 bytes txSetHash + 8 bytes closeTime + 4 bytes upgrades(0) + 4 bytes ext(99)
        bad_sv = (b"\x11" * 32) + (100).to_bytes(8, "big") + (0).to_bytes(4, "big") + (99).to_bytes(4, "big")
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_stellar_value(bad_sv)

    def test_non_zero_padding_rejected(self) -> None:
        # String length 3, followed by 3 chars, plus 1 padding byte which must be 0
        writer = xdr_codec.XdrWriter()
        # ContractExecutable ExternalRef
        # Disc 2, SCAddress contract (1) + 32 bytes, string len 3 + "tag" + pad 0x01
        data = (
            (2).to_bytes(4, "big")
            + (1).to_bytes(4, "big")
            + (b"\x55" * 32)
            + (3).to_bytes(4, "big")
            + b"tag\x01"  # non-zero padding byte
        )
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_contract_executable(data)

    def test_length_prefix_larger_than_input(self) -> None:
        # Length prefix claims 1000 bytes, but buffer has 4 bytes
        bad_len = (2).to_bytes(4, "big") + (1).to_bytes(4, "big") + (b"\x55" * 32) + (1000).to_bytes(4, "big")
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_contract_executable(bad_len)

    def test_flipped_bits_rejected(self) -> None:
        # Test flipping bits in StellarValue basic
        valid = base64.b64decode("EREREREREREREREREREREREREREREREREREREREREREAAAAAaOd4AAAAAAAAAAAA")
        # Flip bit in upgrades count (offset 43) -> count becomes 1, input lacks upgrade entry
        corrupted = bytearray(valid)
        corrupted[43] ^= 1
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_stellar_value(bytes(corrupted))

        # Flip bit in ext discriminant (offset 47) -> becomes discriminant 1 (SIGNED), lacks signature
        corrupted2 = bytearray(valid)
        corrupted2[47] ^= 1
        with self.assertRaises(xdr_codec.XdrCodecError):
            xdr_codec.decode_stellar_value(bytes(corrupted2))


if __name__ == "__main__":
    unittest.main()
