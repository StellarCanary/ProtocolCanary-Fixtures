---
name: Bug report
about: A fixture is incorrect, or the validator misbehaves
title: ""
labels: bug
---

## Summary

What's wrong — an incorrect fixture value, a validator false positive/negative, or something else?

## Fixture(s) affected

Path(s) under `protocol-*/`, e.g. `protocol-28/xdr/cap-0083/p28-xdr-cap83-empty-tx-set.toml`.

## Reproduction

```
python3 tools/validate/validate.py
```

or the `Protocol-Canary` command you ran against this fixture directory.

## Expected vs. actual

## Environment

- Python version:
- `Protocol-Canary` version tested against (if relevant):
