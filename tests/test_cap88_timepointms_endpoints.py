"""Focused tests for CAP-88 TimePointMs unsigned encoding endpoints (issue #538).

Exercises zero and maximum uint64 (18446744073709551615) for both CAP-88 arms:
- STELLAR_VALUE_SIGNED_MS (discriminant 3)
- STELLAR_VALUE_EMPTY_TX_SET_MS (discriminant 4)

Asserts:
- TimePointMs.$value is 0 or 18446744073709551615.
- closeTimeMs is 0 or 18446744073709551615.
- closeTime is 0 or 18446744073709551 (floor(closeTimeMs / 1000)).
- Decoded fields and exact byte-for-byte roundtrip with both decoders/encoders.
- Structural rejections (truncation, trailing bytes, invalid discriminants)
  are rejected by both decoders.
"""
from __future__ import annotations

import base64
import sys
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests import xdr_codec

CAMPAIGN_DIR = REPO_ROOT / "protocol-30" / "xdr" / "campaign"
SIGNED_ZERO_PATH = CAMPAIGN_DIR / "p30-xdr-cap88-timepointms-endpoints-signed-zero.toml"
PROPOSED_ZERO_PATH = CAMPAIGN_DIR / "p30-xdr-cap88-timepointms-endpoints-proposed-zero.toml"
SIGNED_MAX_PATH = CAMPAIGN_DIR / "p30-xdr-cap88-timepointms-endpoints-signed-maximum.toml"
PROPOSED_MAX_PATH = CAMPAIGN_DIR / "p30-xdr-cap88-timepointms-endpoints-proposed-maximum.toml"

MAX_UINT64 = 18446744073709551615
MAX_CLOSE_TIME = 18446744073709551  # floor(18446744073709551615 / 1000)


def load_xdr_fixture(path: Path) -> tuple[dict, bytes]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data, base64.b64decode(data["value_base64"], validate=True)


class Cap88TimePointMsEndpointsTests(unittest.TestCase):
    def test_signed_zero_endpoint(self) -> None:
        data, raw = load_xdr_fixture(SIGNED_ZERO_PATH)
        self.assertEqual(data["id"], "p30-xdr-cap88-timepointms-endpoints-signed-zero")
        self.assertEqual(data["protocol"], 30)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "cap-0088")
        self.assertEqual(data["type"], "StellarValue")
        self.assertEqual(data["kind"], "roundtrip")

        # Decode with both the type-specific and generic XDR decoders
        decoded = xdr_codec.decode_stellar_value(raw)
        decoded_generic = xdr_codec.decode_xdr("StellarValue", raw)
        self.assertEqual(decoded, decoded_generic)

        # Field assertions
        self.assertEqual(decoded.tx_set_hash, bytes([0x11]) * 32)
        self.assertEqual(decoded.upgrades, [])
        self.assertEqual(decoded.ext.ext_type, xdr_codec.STELLAR_VALUE_SIGNED_MS)
        self.assertIsNotNone(decoded.ext.signed_ms_value)

        signed_ms = decoded.ext.signed_ms_value
        self.assertIsNotNone(signed_ms)
        # Assert TimePointMs.$value is 0 and closeTimeMs is 0
        self.assertEqual(signed_ms.close_time_ms, 0)
        # Assert closeTime is 0
        self.assertEqual(decoded.close_time, 0)
        # Assert integer division closeTime == floor(closeTimeMs / 1000)
        self.assertEqual(decoded.close_time, signed_ms.close_time_ms // 1000)

        # Sentinel signature verification
        self.assertEqual(
            signed_ms.lc_value_signature.node_id.key_type,
            xdr_codec.PUBLIC_KEY_TYPE_ED25519,
        )
        self.assertEqual(
            signed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32
        )
        self.assertEqual(
            signed_ms.lc_value_signature.signature, bytes([0x55]) * 64
        )

        # Exact byte roundtrip with both encoders
        self.assertEqual(raw, xdr_codec.encode_stellar_value(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("StellarValue", decoded))

    def test_proposed_zero_endpoint(self) -> None:
        data, raw = load_xdr_fixture(PROPOSED_ZERO_PATH)
        self.assertEqual(data["id"], "p30-xdr-cap88-timepointms-endpoints-proposed-zero")
        self.assertEqual(data["protocol"], 30)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "cap-0088")
        self.assertEqual(data["type"], "StellarValue")
        self.assertEqual(data["kind"], "roundtrip")

        # Decode with both decoders
        decoded = xdr_codec.decode_stellar_value(raw)
        decoded_generic = xdr_codec.decode_xdr("StellarValue", raw)
        self.assertEqual(decoded, decoded_generic)

        # Field assertions
        self.assertEqual(decoded.tx_set_hash, bytes(32))
        self.assertEqual(decoded.upgrades, [])
        self.assertEqual(decoded.ext.ext_type, xdr_codec.STELLAR_VALUE_EMPTY_TX_SET_MS)
        self.assertIsNotNone(decoded.ext.proposed_ms_value)

        proposed_ms = decoded.ext.proposed_ms_value
        self.assertIsNotNone(proposed_ms)
        # Assert TimePointMs.$value is 0 and closeTimeMs is 0
        self.assertEqual(proposed_ms.close_time_ms, 0)
        # Assert closeTime is 0
        self.assertEqual(decoded.close_time, 0)
        # Assert integer division closeTime == floor(closeTimeMs / 1000)
        self.assertEqual(decoded.close_time, proposed_ms.close_time_ms // 1000)

        # Proposed value arm fields
        self.assertEqual(proposed_ms.tx_set_hash, bytes([0x33]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_hash, bytes([0x44]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_version, 30)
        self.assertEqual(
            proposed_ms.lc_value_signature.node_id.key_type,
            xdr_codec.PUBLIC_KEY_TYPE_ED25519,
        )
        self.assertEqual(
            proposed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32
        )
        self.assertEqual(
            proposed_ms.lc_value_signature.signature, bytes([0x55]) * 64
        )

        # Exact byte roundtrip with both encoders
        self.assertEqual(raw, xdr_codec.encode_stellar_value(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("StellarValue", decoded))

    def test_signed_maximum_endpoint(self) -> None:
        data, raw = load_xdr_fixture(SIGNED_MAX_PATH)
        self.assertEqual(data["id"], "p30-xdr-cap88-timepointms-endpoints-signed-maximum")
        self.assertEqual(data["protocol"], 30)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "cap-0088")
        self.assertEqual(data["type"], "StellarValue")
        self.assertEqual(data["kind"], "roundtrip")

        # Decode with both decoders
        decoded = xdr_codec.decode_stellar_value(raw)
        decoded_generic = xdr_codec.decode_xdr("StellarValue", raw)
        self.assertEqual(decoded, decoded_generic)

        # Field assertions
        self.assertEqual(decoded.tx_set_hash, bytes([0x11]) * 32)
        self.assertEqual(decoded.upgrades, [])
        self.assertEqual(decoded.ext.ext_type, xdr_codec.STELLAR_VALUE_SIGNED_MS)
        self.assertIsNotNone(decoded.ext.signed_ms_value)

        signed_ms = decoded.ext.signed_ms_value
        self.assertIsNotNone(signed_ms)
        # Assert TimePointMs.$value is 18446744073709551615 and closeTimeMs is 18446744073709551615
        self.assertEqual(signed_ms.close_time_ms, MAX_UINT64)
        # Assert closeTime is 18446744073709551
        self.assertEqual(decoded.close_time, MAX_CLOSE_TIME)
        # Assert integer division closeTime == floor(closeTimeMs / 1000)
        self.assertEqual(decoded.close_time, signed_ms.close_time_ms // 1000)

        # Sentinel signature verification
        self.assertEqual(
            signed_ms.lc_value_signature.node_id.key_type,
            xdr_codec.PUBLIC_KEY_TYPE_ED25519,
        )
        self.assertEqual(
            signed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32
        )
        self.assertEqual(
            signed_ms.lc_value_signature.signature, bytes([0x55]) * 64
        )

        # Exact byte roundtrip with both encoders
        self.assertEqual(raw, xdr_codec.encode_stellar_value(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("StellarValue", decoded))

    def test_proposed_maximum_endpoint(self) -> None:
        data, raw = load_xdr_fixture(PROPOSED_MAX_PATH)
        self.assertEqual(data["id"], "p30-xdr-cap88-timepointms-endpoints-proposed-maximum")
        self.assertEqual(data["protocol"], 30)
        self.assertEqual(data["surface"], "xdr")
        self.assertEqual(data["category"], "cap-0088")
        self.assertEqual(data["type"], "StellarValue")
        self.assertEqual(data["kind"], "roundtrip")

        # Decode with both decoders
        decoded = xdr_codec.decode_stellar_value(raw)
        decoded_generic = xdr_codec.decode_xdr("StellarValue", raw)
        self.assertEqual(decoded, decoded_generic)

        # Field assertions
        self.assertEqual(decoded.tx_set_hash, bytes(32))
        self.assertEqual(decoded.upgrades, [])
        self.assertEqual(decoded.ext.ext_type, xdr_codec.STELLAR_VALUE_EMPTY_TX_SET_MS)
        self.assertIsNotNone(decoded.ext.proposed_ms_value)

        proposed_ms = decoded.ext.proposed_ms_value
        self.assertIsNotNone(proposed_ms)
        # Assert TimePointMs.$value is 18446744073709551615 and closeTimeMs is 18446744073709551615
        self.assertEqual(proposed_ms.close_time_ms, MAX_UINT64)
        # Assert closeTime is 18446744073709551
        self.assertEqual(decoded.close_time, MAX_CLOSE_TIME)
        # Assert integer division closeTime == floor(closeTimeMs / 1000)
        self.assertEqual(decoded.close_time, proposed_ms.close_time_ms // 1000)

        # Proposed value arm fields
        self.assertEqual(proposed_ms.tx_set_hash, bytes([0x33]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_hash, bytes([0x44]) * 32)
        self.assertEqual(proposed_ms.previous_ledger_version, 30)
        self.assertEqual(
            proposed_ms.lc_value_signature.node_id.key_type,
            xdr_codec.PUBLIC_KEY_TYPE_ED25519,
        )
        self.assertEqual(
            proposed_ms.lc_value_signature.node_id.ed25519, bytes([0x66]) * 32
        )
        self.assertEqual(
            proposed_ms.lc_value_signature.signature, bytes([0x55]) * 64
        )

        # Exact byte roundtrip with both encoders
        self.assertEqual(raw, xdr_codec.encode_stellar_value(decoded))
        self.assertEqual(raw, xdr_codec.encode_xdr("StellarValue", decoded))

    def test_rejected_cases_with_both_decoders(self) -> None:
        decoders = [
            ("decode_stellar_value", xdr_codec.decode_stellar_value),
            ("decode_xdr", lambda b: xdr_codec.decode_xdr("StellarValue", b)),
        ]

        fixtures = [
            SIGNED_ZERO_PATH,
            PROPOSED_ZERO_PATH,
            SIGNED_MAX_PATH,
            PROPOSED_MAX_PATH,
        ]

        for path in fixtures:
            _, raw = load_xdr_fixture(path)

            for decoder_name, decoder in decoders:
                with self.subTest(fixture=path.name, decoder=decoder_name, case="truncation_1"):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decoder(raw[:-1])

                with self.subTest(fixture=path.name, decoder=decoder_name, case="truncation_4"):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decoder(raw[:-4])

                with self.subTest(fixture=path.name, decoder=decoder_name, case="truncation_interior"):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decoder(raw[:40])

                with self.subTest(fixture=path.name, decoder=decoder_name, case="trailing_bytes_1"):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decoder(raw + b"\x00")

                with self.subTest(fixture=path.name, decoder=decoder_name, case="trailing_bytes_4"):
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decoder(raw + b"\x00\x00\x00\x00")

                with self.subTest(fixture=path.name, decoder=decoder_name, case="invalid_discriminant"):
                    # Offset 40..44 is the ext discriminant in these fixtures (32 bytes hash + 8 bytes close_time + 4 bytes upgrades length 0)
                    mutated = bytearray(raw)
                    mutated[40:44] = (99).to_bytes(4, "big")
                    with self.assertRaises(xdr_codec.XdrCodecError):
                        decoder(bytes(mutated))

    def test_encoder_rejects_out_of_range_timepointms(self) -> None:
        _, signed_raw = load_xdr_fixture(SIGNED_ZERO_PATH)
        signed = xdr_codec.decode_stellar_value(signed_raw)
        self.assertIsNotNone(signed.ext.signed_ms_value)

        encoders = [
            ("encode_stellar_value", xdr_codec.encode_stellar_value),
            ("encode_xdr", lambda v: xdr_codec.encode_xdr("StellarValue", v)),
        ]

        for encoder_name, encoder in encoders:
            # Greater than uint64 MAX (1 << 64)
            invalid_overflow = replace(
                signed,
                ext=replace(
                    signed.ext,
                    signed_ms_value=replace(
                        signed.ext.signed_ms_value, close_time_ms=1 << 64
                    ),
                ),
            )
            with self.subTest(encoder=encoder_name, case="overflow_signed"):
                with self.assertRaises(xdr_codec.XdrCodecError):
                    encoder(invalid_overflow)

            # Negative
            invalid_negative = replace(
                signed,
                ext=replace(
                    signed.ext,
                    signed_ms_value=replace(
                        signed.ext.signed_ms_value, close_time_ms=-1
                    ),
                ),
            )
            with self.subTest(encoder=encoder_name, case="negative_signed"):
                with self.assertRaises(xdr_codec.XdrCodecError):
                    encoder(invalid_negative)

        _, proposed_raw = load_xdr_fixture(PROPOSED_ZERO_PATH)
        proposed = xdr_codec.decode_stellar_value(proposed_raw)
        self.assertIsNotNone(proposed.ext.proposed_ms_value)

        for encoder_name, encoder in encoders:
            invalid_overflow = replace(
                proposed,
                ext=replace(
                    proposed.ext,
                    proposed_ms_value=replace(
                        proposed.ext.proposed_ms_value, close_time_ms=1 << 64
                    ),
                ),
            )
            with self.subTest(encoder=encoder_name, case="overflow_proposed"):
                with self.assertRaises(xdr_codec.XdrCodecError):
                    encoder(invalid_overflow)

            invalid_negative = replace(
                proposed,
                ext=replace(
                    proposed.ext,
                    proposed_ms_value=replace(
                        proposed.ext.proposed_ms_value, close_time_ms=-1
                    ),
                ),
            )
            with self.subTest(encoder=encoder_name, case="negative_proposed"):
                with self.assertRaises(xdr_codec.XdrCodecError):
                    encoder(invalid_negative)


if __name__ == "__main__":
    unittest.main()
