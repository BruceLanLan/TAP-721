# Contributing

Thanks for helping. Two kinds of contribution go to two places.

## Changes to the standards (the TAP texts)

The drafts in `TAPs/` are proposals for the [TapeOut TAPs](https://github.com/TapeOutProtocol/TAPs)
repository and follow TAP-01. They were submitted on 2026-10-18 and are in **Draft**, awaiting editor format
review and number assignment (`tap: TBD`; number 721 is requested for the flagship, and the editors may assign
another):

1. Discussion of the whole family happens in the **Idea issue**
   [TapeOutProtocol/TAPs#66](https://github.com/TapeOutProtocol/TAPs/issues/66), which every draft's
   `discussions-to` field points to.
2. Each draft has **its own PR**: flagship [#67](https://github.com/TapeOutProtocol/TAPs/pull/67), bridging
   [#68](https://github.com/TapeOutProtocol/TAPs/pull/68), PoD attributes
   [#69](https://github.com/TapeOutProtocol/TAPs/pull/69), structural hash
   [#70](https://github.com/TapeOutProtocol/TAPs/pull/70). Comments on the text belong there.
3. The English text is normative. Keep the `.zh.md` translation in step in the same change.

Small fixes to the drafts (typos, broken references, inconsistencies with the vectors) are welcome here as
issues or PRs; they are carried over to the open TAPs PRs.

## Changes to the code, vectors and tools

- Open an issue or a PR in this repository.
- Run the suites you touch (see [docs/TESTING.md](docs/TESTING.md); Python 3.9+, Foundry v1.8.3, Node 20+); CI runs
  the offline ones on every push.
- Vectors are generated, never edited by hand: change the generator (`make_vectors.py`,
  `make_core_fixtures.py`), regenerate, and commit both. Generators are deterministic, so a clean
  `git status` after regeneration is part of the check.
- Solidity: 0.8.28, optimizer 10,000 runs, EVM `shanghai`; no external libraries besides forge-std for tests.
- Never commit private keys, mnemonics, API keys or RPC URLs that carry a key.
- Security issues: see [docs/SECURITY.md](docs/SECURITY.md).
- Contact: X [@BruceBlue](https://x.com/BruceBlue), GitHub [@BruceLanLan](https://github.com/BruceLanLan).

By contributing you agree that your contribution is licensed as described in [NOTICE](NOTICE)
(CC0-1.0 for TAP texts and data, MIT for code).

## Maintainers: syncing from the working folder

The drafts are developed in a separate working folder. `scripts/sync-from-drafts.sh SOURCE_DIR` (the path is required) copies the
publishable parts into this repository (mirroring with `--delete`, excluding build output and caches) and
aborts without copying anything if a secret-like string is found in the source.
