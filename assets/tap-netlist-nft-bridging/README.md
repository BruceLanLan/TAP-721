# Vectors for the draft "Moving Netlist-Bound NFTs between TapeOut chains"

- `make_vectors.py` — pure Python (own keccak, no dependencies). Writes `vectors.json`; `python3 make_vectors.py --check` regenerates it and fails unless the bytes are identical.
- `vectors.json` — collection keys, valid and invalid payloads, LayerZero options, EIP-712 values for the hub profile, selectors, ERC-165 identifiers and event topics. The Solidity tests in `contracts/test/bridge/TapBridgeVectors.t.sol` read the same values.

SHA-256 of `vectors.json`: `bcfd12c1a2f6d875ce602da32632c260afcd6c5b560a97297044f1f690224f51`

Code in this folder is MIT; data is CC0.
