# Protocol 30 Testnet RPC evidence

The [November 4 Action run](https://github.com/StellarCanary/ProtocolCanary-Action/actions/runs/41810837579)
reported `protocolVersion = 30` on Testnet, while the pinned Protocol 29
fixture expected 29. The Futurenet Protocol 29 check passed in that run.
The [Bell upgrade guide](https://stellar.org/blog/developers/bell-protocol-30-upgrade-guide)
records the Testnet upgrade date.

This candidate uses `getVersionInfo` to check one Protocol 30 Testnet
version field. Its exact live request, response, UTC timestamp, host,
network identity and verification record must come from the existing
read-only tool, not from a mocked test or a manually invented record.

```bash
python3 tools/evidence/capture_live.py protocol-30 \
  --endpoint soroban-testnet.stellar.org \
  --output-dir protocol-30/evidence/live/testnet \
  --require-matched
python3 tools/validate/validate.py protocol-30 \
  --evidence protocol-30/evidence/live/testnet/records
```

The capture tool calls only approved read-only methods, checks the Testnet
network passphrase, and refuses mismatched results. A captured version
number is evidence only for that endpoint and timestamp. It is not
proof that Protocol 30's XDR and other features work.

Do not change or rewrite Protocol 29 evidence. The upstream version
matrix includes Protocol 30.

## Action weekly live workflow

[ProtocolCanary-Action PR #554](https://github.com/StellarCanary/ProtocolCanary-Action/pull/554),
merged on 2026-11-05 at 07:53 UTC, split the Action's weekly live workflow
into two separate network checks with their own fixture pins:

- **Testnet, Protocol 30 RPC identity.** The leg checks out this repository
  at commit `9feb1a85f64cd43201685fe233bf9ef15a38a752` (the merge of this
  repository's PR #489) and runs `protocol-30/`. It asserts only that
  Testnet's `getVersionInfo` reports `protocolVersion = 30`. That commit is
  not a released fixture pack.
- **Futurenet, Protocol 29.** The leg keeps the published Protocol 29 pack,
  `fixtures-p29-v0.1.1` (commit `347ad6846d46b7bdf605a299501354563d79f2d9`),
  because Futurenet reported Protocol 29 when the PR was merged.

The first run after the merge,
[run 41990892418](https://github.com/StellarCanary/ProtocolCanary-Action/actions/runs/41990892418)
(manual dispatch on `main` at the merge commit, 2026-11-05 07:57 UTC),
succeeded: the "Live canary (Protocol 30 testnet)" and "Live canary
(Protocol 29 futurenet)" jobs both passed.

These are two independent RPC checks, one per network. Neither is evidence
of full Protocol 30 compatibility: they do not verify Protocol 30 XDR,
Soroban or transaction behaviour, and they make no claim about Mainnet.
The run does not change the verification records in this repository.
This page records that one run; later scheduled results are in the
[workflow's run history](https://github.com/StellarCanary/ProtocolCanary-Action/actions/workflows/weekly-live.yml).
