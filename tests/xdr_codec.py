"""Independent pure-Python XDR codec for StellarValue and ContractExecutable (F-083).

Transcribed strictly according to RFC 4506 from the authoritative XDR
definitions in ``stellar/stellar-xdr`` at tag ``v28.0`` (commit
``9c9c145953e80990d6ff1ae3a6a973a0ce6d0694``):

- ``Stellar-ledger.x``:
  - ``enum StellarValueType`` (lines 14-19)
  - ``struct LedgerCloseValueSignature`` (lines 20-24)
  - ``struct StellarValue`` (lines 26-57)
  - ``union switch (StellarValueType v)`` (lines 41-56)
- ``Stellar-types.x``:
  - ``typedef opaque Hash[32]`` (line 10)
  - ``typedef uint64 TimePoint`` (line 14)
  - ``union PublicKey switch (PublicKeyType type)`` (lines 53-57)
  - ``typedef opaque Signature<64>`` (line 80)
  - ``typedef PublicKey NodeID`` (line 84)
  - ``typedef opaque UpgradeType<128>`` (line 94)
- ``Stellar-contract.x``:
  - ``union SCAddress switch (SCAddressType type)`` (lines 85-95)
  - ``typedef string SCString<>`` (line 104)
  - ``enum ContractExecutableType`` (lines 172-177)
  - ``struct ContractExecutableExternalRef`` (lines 182-185)
  - ``union ContractExecutable switch (ContractExecutableType type)`` (lines 229-237)

Strict RFC 4506 rules implemented:
- All integer and length values are 4-byte or 8-byte big-endian.
- Variable-length opaque and string data must be padded to a 4-byte boundary
  with zero bytes (non-zero padding is rejected).
- Trailing bytes after the top-level structure are rejected.
- Truncated inputs and length prefixes exceeding the remaining buffer are rejected.
- Unknown union discriminants are rejected.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Union


class XdrCodecError(ValueError):
    """Raised when XDR input violates RFC 4506 encoding or type definition rules."""


# ---------------------------------------------------------------- Data Models

# PublicKeyType
PUBLIC_KEY_TYPE_ED25519 = 0


@dataclass(frozen=True)
class PublicKey:
    key_type: int
    ed25519: bytes  # 32 bytes


@dataclass(frozen=True)
class LedgerCloseValueSignature:
    node_id: PublicKey
    signature: bytes  # max 64 bytes


# StellarValueType
STELLAR_VALUE_BASIC = 0
STELLAR_VALUE_SIGNED = 1
STELLAR_VALUE_EMPTY_TX_SET = 2


@dataclass(frozen=True)
class EmptyTxSetProposedValue:
    tx_set_hash: bytes  # 32 bytes
    previous_ledger_hash: bytes  # 32 bytes
    previous_ledger_version: int  # uint32
    lc_value_signature: LedgerCloseValueSignature


@dataclass(frozen=True)
class StellarValueExt:
    ext_type: int  # StellarValueType
    signature: LedgerCloseValueSignature | None = None  # SIGNED
    proposed_value: EmptyTxSetProposedValue | None = None  # EMPTY_TX_SET


@dataclass(frozen=True)
class StellarValue:
    tx_set_hash: bytes  # 32 bytes
    close_time: int  # uint64
    upgrades: list[bytes]  # list of UpgradeType (opaque<128>)
    ext: StellarValueExt


# ContractExecutableType
CONTRACT_EXECUTABLE_WASM = 0
CONTRACT_EXECUTABLE_STELLAR_ASSET = 1
CONTRACT_EXECUTABLE_EXTERNAL_REF = 2

# SCAddressType
SC_ADDRESS_TYPE_ACCOUNT = 0
SC_ADDRESS_TYPE_CONTRACT = 1


@dataclass(frozen=True)
class SCAddress:
    address_type: int
    account_id: PublicKey | None = None  # for SC_ADDRESS_TYPE_ACCOUNT
    contract_id: bytes | None = None  # 32 bytes for SC_ADDRESS_TYPE_CONTRACT


@dataclass(frozen=True)
class ContractExecutableExternalRef:
    executable_owner: SCAddress
    tag: str


@dataclass(frozen=True)
class ContractExecutable:
    executable_type: int
    wasm_hash: bytes | None = None  # for CONTRACT_EXECUTABLE_WASM (32 bytes)
    external_ref: ContractExecutableExternalRef | None = None  # for CONTRACT_EXECUTABLE_EXTERNAL_REF


# ---------------------------------------------------------------- Wire Buffer

class XdrReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def _require(self, n: int, field_name: str = "data") -> None:
        if self.pos + n > len(self.data):
            needed = self.pos + n
            have = len(self.data)
            raise XdrCodecError(
                f"truncated input reading {field_name}: need {needed} bytes, have {have}"
            )

    def read_int32(self) -> int:
        self._require(4, "int32")
        val = struct.unpack(">i", self.data[self.pos:self.pos + 4])[0]
        self.pos += 4
        return val

    def read_uint32(self) -> int:
        self._require(4, "uint32")
        val = struct.unpack(">I", self.data[self.pos:self.pos + 4])[0]
        self.pos += 4
        return val

    def read_uint64(self) -> int:
        self._require(8, "uint64")
        val = struct.unpack(">Q", self.data[self.pos:self.pos + 8])[0]
        self.pos += 8
        return val

    def read_fixed_opaque(self, n: int) -> bytes:
        self._require(n, f"fixed opaque ({n} bytes)")
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        padding = (4 - (n % 4)) % 4
        if padding > 0:
            self._require(padding, "padding")
            pad_bytes = self.data[self.pos:self.pos + padding]
            if pad_bytes != b"\x00" * padding:
                raise XdrCodecError(
                    f"non-zero padding in fixed opaque: expected zeros, got {pad_bytes!r}"
                )
            self.pos += padding
        return raw

    def read_var_opaque(self, max_length: int | None = None) -> bytes:
        length = self.read_uint32()
        if max_length is not None and length > max_length:
            raise XdrCodecError(
                f"length prefix {length} exceeds maximum allowed {max_length}"
            )
        self._require(length, f"var opaque payload ({length} bytes)")
        raw = self.data[self.pos:self.pos + length]
        self.pos += length
        padding = (4 - (length % 4)) % 4
        if padding > 0:
            self._require(padding, "var opaque padding")
            pad_bytes = self.data[self.pos:self.pos + padding]
            if pad_bytes != b"\x00" * padding:
                raise XdrCodecError(
                    f"non-zero padding in variable-length opaque: got {pad_bytes!r}"
                )
            self.pos += padding
        return raw

    def read_string(self, max_length: int | None = None) -> str:
        raw_bytes = self.read_var_opaque(max_length)
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise XdrCodecError(f"invalid UTF-8 in string: {exc}") from None

    def assert_eof(self) -> None:
        if self.pos < len(self.data):
            trailing = len(self.data) - self.pos
            raise XdrCodecError(
                f"trailing bytes after XDR structure: {trailing} unconsumed byte(s)"
            )


class XdrWriter:
    def __init__(self) -> None:
        self.buf = bytearray()

    def write_int32(self, val: int) -> None:
        self.buf.extend(struct.pack(">i", val))

    def write_uint32(self, val: int) -> None:
        self.buf.extend(struct.pack(">I", val))

    def write_uint64(self, val: int) -> None:
        self.buf.extend(struct.pack(">Q", val))

    def write_fixed_opaque(self, data: bytes) -> None:
        self.buf.extend(data)
        padding = (4 - (len(data) % 4)) % 4
        if padding > 0:
            self.buf.extend(b"\x00" * padding)

    def write_var_opaque(self, data: bytes, max_length: int | None = None) -> None:
        if max_length is not None and len(data) > max_length:
            raise XdrCodecError(
                f"length {len(data)} exceeds maximum allowed {max_length}"
            )
        self.write_uint32(len(data))
        self.write_fixed_opaque(data)

    def write_string(self, text: str, max_length: int | None = None) -> None:
        raw = text.encode("utf-8")
        self.write_var_opaque(raw, max_length)

    def to_bytes(self) -> bytes:
        return bytes(self.buf)


# ------------------------------------------------------------ Helpers

def _decode_public_key(reader: XdrReader) -> PublicKey:
    pk_type = reader.read_int32()
    if pk_type != PUBLIC_KEY_TYPE_ED25519:
        raise XdrCodecError(f"unknown PublicKeyType discriminant: {pk_type}")
    ed25519 = reader.read_fixed_opaque(32)
    return PublicKey(key_type=pk_type, ed25519=ed25519)


def _encode_public_key(writer: XdrWriter, pk: PublicKey) -> None:
    if pk.key_type != PUBLIC_KEY_TYPE_ED25519:
        raise XdrCodecError(f"unknown PublicKeyType discriminant: {pk.key_type}")
    writer.write_int32(pk.key_type)
    if len(pk.ed25519) != 32:
        raise XdrCodecError(f"ed25519 key must be 32 bytes, got {len(pk.ed25519)}")
    writer.write_fixed_opaque(pk.ed25519)


def _decode_lc_value_signature(reader: XdrReader) -> LedgerCloseValueSignature:
    node_id = _decode_public_key(reader)
    sig = reader.read_var_opaque(max_length=64)
    return LedgerCloseValueSignature(node_id=node_id, signature=sig)


def _encode_lc_value_signature(writer: XdrWriter, lcs: LedgerCloseValueSignature) -> None:
    _encode_public_key(writer, lcs.node_id)
    writer.write_var_opaque(lcs.signature, max_length=64)


def _decode_sc_address(reader: XdrReader) -> SCAddress:
    addr_type = reader.read_int32()
    if addr_type == SC_ADDRESS_TYPE_ACCOUNT:
        account_id = _decode_public_key(reader)
        return SCAddress(address_type=addr_type, account_id=account_id)
    elif addr_type == SC_ADDRESS_TYPE_CONTRACT:
        contract_id = reader.read_fixed_opaque(32)
        return SCAddress(address_type=addr_type, contract_id=contract_id)
    else:
        raise XdrCodecError(f"unknown SCAddressType discriminant: {addr_type}")


def _encode_sc_address(writer: XdrWriter, addr: SCAddress) -> None:
    writer.write_int32(addr.address_type)
    if addr.address_type == SC_ADDRESS_TYPE_ACCOUNT:
        if addr.account_id is None:
            raise XdrCodecError("account_id required for SC_ADDRESS_TYPE_ACCOUNT")
        _encode_public_key(writer, addr.account_id)
    elif addr.address_type == SC_ADDRESS_TYPE_CONTRACT:
        if addr.contract_id is None or len(addr.contract_id) != 32:
            raise XdrCodecError("contract_id (32 bytes) required for SC_ADDRESS_TYPE_CONTRACT")
        writer.write_fixed_opaque(addr.contract_id)
    else:
        raise XdrCodecError(f"unknown SCAddressType discriminant: {addr.address_type}")


# ------------------------------------------------- StellarValue Codec

def decode_stellar_value(raw: bytes) -> StellarValue:
    reader = XdrReader(raw)
    tx_set_hash = reader.read_fixed_opaque(32)
    close_time = reader.read_uint64()

    upgrade_count = reader.read_uint32()
    if upgrade_count > 6:
        raise XdrCodecError(f"upgrades count {upgrade_count} exceeds maximum 6")
    upgrades: list[bytes] = []
    for _ in range(upgrade_count):
        upgrades.append(reader.read_var_opaque(max_length=128))

    ext_type = reader.read_int32()
    if ext_type == STELLAR_VALUE_BASIC:
        ext = StellarValueExt(ext_type=ext_type)
    elif ext_type == STELLAR_VALUE_SIGNED:
        sig = _decode_lc_value_signature(reader)
        ext = StellarValueExt(ext_type=ext_type, signature=sig)
    elif ext_type == STELLAR_VALUE_EMPTY_TX_SET:
        proposed_tx_set_hash = reader.read_fixed_opaque(32)
        prev_ledger_hash = reader.read_fixed_opaque(32)
        prev_ledger_ver = reader.read_uint32()
        lc_sig = _decode_lc_value_signature(reader)
        proposed = EmptyTxSetProposedValue(
            tx_set_hash=proposed_tx_set_hash,
            previous_ledger_hash=prev_ledger_hash,
            previous_ledger_version=prev_ledger_ver,
            lc_value_signature=lc_sig,
        )
        ext = StellarValueExt(ext_type=ext_type, proposed_value=proposed)
    else:
        raise XdrCodecError(f"unknown StellarValueType discriminant: {ext_type}")

    reader.assert_eof()
    return StellarValue(
        tx_set_hash=tx_set_hash,
        close_time=close_time,
        upgrades=upgrades,
        ext=ext,
    )


def encode_stellar_value(val: StellarValue) -> bytes:
    writer = XdrWriter()
    if len(val.tx_set_hash) != 32:
        raise XdrCodecError(f"txSetHash must be 32 bytes, got {len(val.tx_set_hash)}")
    writer.write_fixed_opaque(val.tx_set_hash)
    writer.write_uint64(val.close_time)

    if len(val.upgrades) > 6:
        raise XdrCodecError(f"upgrades count {len(val.upgrades)} exceeds maximum 6")
    writer.write_uint32(len(val.upgrades))
    for u in val.upgrades:
        writer.write_var_opaque(u, max_length=128)

    writer.write_int32(val.ext.ext_type)
    if val.ext.ext_type == STELLAR_VALUE_BASIC:
        pass
    elif val.ext.ext_type == STELLAR_VALUE_SIGNED:
        if val.ext.signature is None:
            raise XdrCodecError("signature required for STELLAR_VALUE_SIGNED")
        _encode_lc_value_signature(writer, val.ext.signature)
    elif val.ext.ext_type == STELLAR_VALUE_EMPTY_TX_SET:
        pv = val.ext.proposed_value
        if pv is None:
            raise XdrCodecError("proposed_value required for STELLAR_VALUE_EMPTY_TX_SET")
        if len(pv.tx_set_hash) != 32:
            raise XdrCodecError("proposed txSetHash must be 32 bytes")
        writer.write_fixed_opaque(pv.tx_set_hash)
        if len(pv.previous_ledger_hash) != 32:
            raise XdrCodecError("previousLedgerHash must be 32 bytes")
        writer.write_fixed_opaque(pv.previous_ledger_hash)
        writer.write_uint32(pv.previous_ledger_version)
        _encode_lc_value_signature(writer, pv.lc_value_signature)
    else:
        raise XdrCodecError(f"unknown StellarValueType discriminant: {val.ext.ext_type}")

    return writer.to_bytes()


# --------------------------------------------- ContractExecutable Codec

def decode_contract_executable(raw: bytes) -> ContractExecutable:
    reader = XdrReader(raw)
    exec_type = reader.read_int32()
    if exec_type == CONTRACT_EXECUTABLE_WASM:
        wasm_hash = reader.read_fixed_opaque(32)
        exec_val = ContractExecutable(executable_type=exec_type, wasm_hash=wasm_hash)
    elif exec_type == CONTRACT_EXECUTABLE_STELLAR_ASSET:
        exec_val = ContractExecutable(executable_type=exec_type)
    elif exec_type == CONTRACT_EXECUTABLE_EXTERNAL_REF:
        owner = _decode_sc_address(reader)
        tag = reader.read_string()
        ref = ContractExecutableExternalRef(executable_owner=owner, tag=tag)
        exec_val = ContractExecutable(executable_type=exec_type, external_ref=ref)
    else:
        raise XdrCodecError(f"unknown ContractExecutableType discriminant: {exec_type}")

    reader.assert_eof()
    return exec_val


def encode_contract_executable(val: ContractExecutable) -> bytes:
    writer = XdrWriter()
    writer.write_int32(val.executable_type)
    if val.executable_type == CONTRACT_EXECUTABLE_WASM:
        if val.wasm_hash is None or len(val.wasm_hash) != 32:
            raise XdrCodecError("wasm_hash (32 bytes) required for CONTRACT_EXECUTABLE_WASM")
        writer.write_fixed_opaque(val.wasm_hash)
    elif val.executable_type == CONTRACT_EXECUTABLE_STELLAR_ASSET:
        pass
    elif val.executable_type == CONTRACT_EXECUTABLE_EXTERNAL_REF:
        if val.external_ref is None:
            raise XdrCodecError("external_ref required for CONTRACT_EXECUTABLE_EXTERNAL_REF")
        _encode_sc_address(writer, val.external_ref.executable_owner)
        writer.write_string(val.external_ref.tag)
    else:
        raise XdrCodecError(f"unknown ContractExecutableType discriminant: {val.executable_type}")

    return writer.to_bytes()


# --------------------------------------------------- Generic Interface

def decode_xdr(type_name: str, raw: bytes) -> Any:
    if type_name == "StellarValue":
        return decode_stellar_value(raw)
    elif type_name == "ContractExecutable":
        return decode_contract_executable(raw)
    else:
        raise XdrCodecError(f"unsupported XDR type for independent codec: {type_name}")


def encode_xdr(type_name: str, value: Any) -> bytes:
    if type_name == "StellarValue":
        return encode_stellar_value(value)
    elif type_name == "ContractExecutable":
        return encode_contract_executable(value)
    else:
        raise XdrCodecError(f"unsupported XDR type for independent codec: {type_name}")
