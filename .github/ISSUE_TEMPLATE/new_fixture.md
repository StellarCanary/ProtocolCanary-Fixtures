---
name: New protocol compatibility fixture
about: Propose a new fixture for a protocol pack (e.g. protocol-28)
title: ""
labels: enhancement
---

## Protocol and surface

Protocol version: (e.g. 28)
Surface: `xdr` / `rpc` / `soroban`
Relevant CAP (if any):

## What does this fixture assert?

Describe the specific compatibility behavior being tested — e.g. "a
StellarValue using the CAP-0083 STELLAR_VALUE_EMPTY_TX_SET ext round-trips
byte-for-byte."

## Source / provenance

Link to the CAP, upstream `stellar-xdr` type, or RPC/Soroban behavior this
fixture is derived from. Fixture values must be real, well-typed output
(e.g. from `stellar-xdr`'s `to_xdr_base64`), not hand-assembled bytes —
see the "Provenance" section of the README.

## Validation

- [ ] `python3 tools/validate/validate.py` passes
- [ ] `python3 -m unittest discover tests` passes
- [ ] Verified against a real build of `Protocol-Canary` (state the version
      tested against)

## Out of scope

Anything this fixture deliberately does not cover.
