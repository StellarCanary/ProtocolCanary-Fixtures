# ProtocolCanary-Fixtures

Canonical compatibility fixtures for Stellar Protocol Canary.

## Purpose

This repository answers one question: **what exact Stellar protocol
behavior should Protocol Canary test?**

```text
Protocol specification / upstream implementation
                    |
                    v
            Canonical fixture
                    |
                    v
       ProtocolCanary-Fixtures   <- this repository
                    |
                    v
            Protocol-Canary
                    |
                    v
          Compatibility Result
```

`ProtocolCanary-Fixtures` defines **what** should be tested. The
[`StellarCanary/Protocol-Canary`](https://github.com/StellarCanary/Protocol-Canary)
CLI defines **how** the test is executed. This repository contains no
business logic, no server, no database, and no executable fixture code — it
is a versioned corpus of declarative test data.

## Repository relationship

`Protocol-Canary` loads fixtures with `canary_fixtures::load_directory`,
exposed via:

```bash
stellar-canary check --fixtures-dir <path-to-a-checkout-of-this-repo> --json
```

The loader recursively walks the given directory and parses **every**
`*.toml` file as one fixture — see
[`docs/fixture-contract.md`](https://github.com/StellarCanary/Protocol-Canary/blob/main/docs/fixture-contract.md)
in `Protocol-Canary` for the authoritative, implementation-verified contract
this repository conforms to. Two consequences that shape this repository's
layout:

- **No `manifest.toml` files.** The loader treats every `.toml` file under
  the given directory as a fixture; a separate discovery/enumeration file
  would either be silently ignored (harmless) or, if named `*.toml`, would
  be mis-parsed as a malformed fixture and fail the whole run. Each
  protocol pack instead has a plain `README.md` (ignored by the loader,
  read by humans).
- **Directory names are cosmetic.** `xdr/`, `rpc/`, `soroban/`, `cap-0083/`
  etc. exist for human navigation only; a fixture's `surface`, `protocol`,
  and `category` fields — not its file path — are what the loader and the
  planner act on.

You can point `--fixtures-dir` at this repository's root, or at a single
`protocol-NN/` directory to scope one pack; the loader's protocol filtering
makes a mixed-protocol directory safe either way.

## Protocol packs

| Pack | Status | Notes |
|---|---|---|
| [`protocol-28/`](protocol-28/) | Active | CAP-0083, CAP-0085 (XDR); Protocol 28 RPC identity; a Soroban simulation smoke fixture. See [`docs/protocol-28.md`](docs/protocol-28.md). |
| [`protocol-27/`](protocol-27/) | Not yet populated | See [`protocol-27/README.md`](protocol-27/README.md) — fixtures are added only after their upstream behavior is independently verified, never as placeholders. |

## Fixture format

Every fixture is one TOML file with common metadata plus a surface-specific
body:

```toml
id = "p28-xdr-cap83-empty-tx-set"     # required, unique across the tree
protocol = 28                          # required
surface = "xdr"                        # required: "xdr" | "rpc" | "soroban"
category = "cap-0083"                  # required, free-text
description = "..."                    # required
source_reference = "CAP-0083"          # optional, should be authoritative

# surface-specific fields follow — see docs/protocol-28.md and
# Protocol-Canary's docs/fixture-contract.md for the exact per-surface
# schema (xdr: type/kind/value_base64; rpc: method/[[assert]]; soroban:
# source_account/contract_id/function/[expect]).
```

Fixtures are declarative data, never code: no fixture field is interpreted
as a shell command, script, or executable instruction of any kind.

## Provenance

Every protocol-specific fixture cites a `source_reference` — a CAP number,
an upstream XDR definition, or an official release/API reference — and
carries a header comment explaining what was verified, how, and (for
anything involving a live network call) when and against which endpoint.
No fixture asserts a value that isn't traceable to an authoritative
upstream source; see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Validation

```bash
python3 tools/validate/validate.py
```

Validates schema conformance, unique IDs, protocol/surface enums, source
references, and referenced-file existence for every fixture in the repo.
This is structural validation only — it never executes a compatibility
check itself. CI (`.github/workflows/validate.yml`) runs it, plus
`python3 -m unittest discover tests`, on every push and pull request.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how to add a fixture.

## Security

See [`SECURITY.md`](SECURITY.md). In short: no secrets, no private keys, no
executable fixture code, no transaction submission — fixture files must be
treated as untrusted input by any consumer.
