# Security Policy

## Scope

This policy covers `ProtocolCanary-Fixtures`: the fixture files, JSON
schemas, and the structural validator under `tools/validate/`. It does not
cover `StellarCanary/Protocol-Canary` (the engine that consumes these
fixtures), which has its own security policy.

## Threat model: fixtures are untrusted input

This repository is public, and its fixtures are consumed by a tool that
may run in a project's CI pipeline. Every fixture file must be treated as
untrusted input by any consumer, including `Protocol-Canary` itself:

- **No executable fixture code.** Fixture files are TOML data. There is no
  `shell_command`, `exec`, `script`, `command`, `pre_run`, or `post_run`
  field, and none will be added. A pull request introducing one will be
  rejected regardless of stated purpose.
- **No secrets.** No fixture may contain a private key, seed phrase, or
  funded-account secret. The `soroban` surface's `source_account` field is
  a public account address only, used to build an *unsigned* transaction
  for simulation — never one that is signed or submitted.
- **No transaction submission.** Fixtures may require decoding, encoding,
  or read-only RPC calls (`getNetwork`, `getLatestLedger`) or Soroban
  *simulation*. No fixture may cause `Protocol-Canary` to submit a
  state-changing transaction to any network.
- **Parser-safety in mind.** `decode-failure` fixtures deliberately feed
  malformed input to an XDR decoder; when adding one, prefer inputs that
  exercise a specific, documented rejection (truncation, an invalid
  discriminant) over arbitrary fuzzing payloads, and note in the fixture's
  header comment what kind of malformation it demonstrates.

## Structural validator

`tools/validate/validate.py` only reads fixture files and reports
structural problems (schema conformance, duplicate IDs, missing files). It
never executes a fixture's assertion and never makes a network call.

## Reporting a vulnerability

If you find a security issue in this repository — a fixture that could be
used to smuggle executable content past a consumer's TOML parser, a schema
gap that would let an untrusted `.toml` file crash a validator, or similar
— please open a private report via GitHub's "Report a vulnerability"
feature on this repository rather than filing a public issue. Include a
description of the issue, its impact, and steps to reproduce. We will
acknowledge reports and work with you on a fix and disclosure timeline
before any public write-up.
