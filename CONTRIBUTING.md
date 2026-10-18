# Contributing

Thanks for helping. Two kinds of contribution go to two places.

## Changes to the standards (the TAP texts)

The drafts in `TAPs/` are proposals for the [TapeOut TAPs](https://github.com/TapeOutProtocol/TAPs)
repository and follow TAP-01:

1. Discuss the idea in an **Idea issue** at TapeOutProtocol/TAPs (or in the issue linked from a draft's
   `discussions-to` field once it exists).
2. Each draft is submitted as **its own PR** to TapeOutProtocol/TAPs as `TAPs/TAP-draft-<short-title>.md`
   with `tap: TBD`. Editors assign numbers.
3. The English text is normative. Keep the `.zh.md` translation in step in the same change.

Small fixes to the drafts (typos, broken references, inconsistencies with the vectors) are welcome here as
issues or PRs; they are carried over to the TAPs submission.

## Changes to the code, vectors and tools

- Open an issue or a PR in this repository.
- Run the suites you touch (see [docs/TESTING.md](docs/TESTING.md)); CI runs the offline ones on every push.
- Vectors are generated, never edited by hand: change the generator (`make_vectors.py`,
  `make_core_fixtures.py`), regenerate, and commit both. Generators are deterministic, so a clean
  `git status` after regeneration is part of the check.
- Solidity: 0.8.28, optimizer 10,000 runs, EVM `shanghai`; no external libraries besides forge-std for tests.
- Never commit private keys, mnemonics, API keys or RPC URLs that carry a key.
- Security issues: see [docs/SECURITY.md](docs/SECURITY.md).

By contributing you agree that your contribution is licensed as described in [NOTICE](NOTICE)
(CC0-1.0 for TAP texts and data, MIT for code).

## Maintainers: syncing from the working folder

The drafts are developed in a separate working folder. `scripts/sync-from-drafts.sh SOURCE_DIR` (the path is required) copies the
publishable parts into this repository (mirroring with `--delete`, excluding build output and caches) and
aborts without copying anything if a secret-like string is found in the source.
