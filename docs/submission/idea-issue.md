**Problem.** TapeOut circuits are already ERC-721 tokens, but there is no standard for a *collectible* whose identity is a real circuit: an NFT that carries, next to its image, a netlist that anyone can download, check against the chain, simulate, run in a contract and tape out again. Community write-ups for the first such collection (TapeCode-Test1, 10,000 tokens on X Layer) agree on the idea but differ on field names, hash definitions, how a netlist is checked and how a blind-box reveal is made fair. Without one text, wallets, explorers, indexers and games cannot read two collections the same way, and holders cannot check that a reveal was fair. TapeOut is multi-chain (BNB Smart Chain, Base, X Layer), which makes a shared identifier and file format more pressing.

**Proposal.** A family of drafts, organised the way ERC-721 is: one flagship standard with in-document extensions, plus separate extension TAPs that build on it (as ERC-4906 and ERC-7496 build on ERC-721).

*Flagship — TAP-721 · Netlist-Bound NFTs* (Standards; `TAPs/TAP-draft-netlist-bound-nft.md`):

- **Core.** A self-contained netlist file `tapnet/1` (TAP-02 NAND/LATCH records behind a 16-byte header, REF rejected) whose SHA-256 is the netlist hash; provenance checks against the source circuit (`isCPU`, `circuitInfo`, `netlist`) and its container (`accountOf`); a CAIP-19 token identifier; the `tap` member of token metadata; a manifest whose image and netlist pools are committed by Merkle roots before the seed; a drand-seeded keyed permutation (4-round Feistel with cycle walking) with every assignment input fixed before the seed; conformance levels **L0** (metadata only, reachable by a contract that can only set its base URI) and **L1** (`ITapNetlistNFT`, ERC-165 id `0x282b67f6`, plus ERC-165 and ERC-4906).
- **In-document extensions.** Companion (§8.3, `ITapCompanion` `0x12b40a6c`: L1 for an existing, unchangeable ERC-721, endorsed by its owner); Eval (§8.4, `ITapNetlistEval` `0xec7d7e20`: any contract runs one TAP-02 beat of a token's netlist); TokenSet (§8.5, `ITapNetlistTokenSet` `0x3f7177c7`: collections whose valid tokens are not one contiguous range); container hosting and locking (§8.6, `tap.content`, SHOULD-level rules for content in TapeOut containers).

*Extension TAPs (roadmap; each submitted as its own PR after the flagship):*

1. **Bridging** (Standards): moving TAP-721 tokens between TapeOut chains, hub-and-spoke (gateway on the home chain, mirrors elsewhere), one 320-byte payload, ONE/ALL route policies, a normative LayerZero V2 profile and an informative TAP-10 hub profile (marked [Open]).
2. **Proof-of-Design attributes** (Application): a labelled snapshot of a miner circuit's PoD facts at a pinned BNB Smart Chain block, in `tap.pod` and optionally as ERC-7496 traits, with a functional check against the task's reference circuit.
3. **Structural hash** (Standards): a fingerprint of flat netlists that is unchanged under renumbering, NAND input swaps, dead elements and duplicated elements, so that copies cannot be passed off as different designs.

Why not one document: the flagship holds what every implementer reads together. Bridging depends on a message layer and upgradeable contracts (TAP-01 §5.1 would keep a TAP that depends on them at Candidate until they are sealed), PoD attributes depend on the BNB Smart Chain mining contract, and the structural hash is useful for any netlist. Kept separate, they cannot hold the flagship back, and each follows the one-topic rule.

**Number request.** We ask the editors to consider number **721** for the flagship. ERC-721 became the common base for NFTs because it is one short document that every wallet implements and that later standards extend; this TAP aims to play the same role for netlist-bound NFTs on TapeOut chains, and the matching number makes that relationship obvious to wallet and marketplace developers who already know ERC-721. We understand that TAP-01 §6.1 has editors assign numbers (normally the lowest free number above 10) and that authors do not pick their own. If 721 is not appropriate we accept whatever number the editors assign; "TAP-721" would then remain only a community nickname, and the drafts will use the assigned number everywhere.

**Type.** Flagship: Standards. Extensions: Bridging — Standards; PoD attributes — Application; Structural hash — Standards.

**Builds on.** TAP-02 (netlists), TAP-10 (chains, on-chain names, containers, `tape://`), ERC-165, ERC-173, ERC-721, ERC-4906, CAIP-19. Bridging also uses EIP-712 and LayerZero V2 EndpointV2; PoD attributes use ERC-7496 at a fixed commit.

**Existing material.**

- Drafts, translations, reference implementations and test vectors: https://github.com/BruceLanLan/TAP-721/tree/e4b922969521d21525940bf1dda0634c38a05b4e
- Flagship draft: https://github.com/BruceLanLan/TAP-721/blob/e4b922969521d21525940bf1dda0634c38a05b4e/TAPs/TAP-draft-netlist-bound-nft.md
- Reference implementation: Python (standard library only) for every draft; a Foundry project with the L1 collection, companion, evaluator, bridge endpoints and adapters, and a container lock (198 tests, including PoCs from four internal review passes). Nothing is deployed; the code has been reviewed internally only.
- Test results and vector hashes: https://github.com/BruceLanLan/TAP-721/blob/e4b922969521d21525940bf1dda0634c38a05b4e/docs/TESTING.md
- First adopter: TapeCode-Test1 (X Layer, `0x0e91460d6823c711643e650a9a4c0cc21de41614`), via L0 plus a companion; the plan is being confirmed with its founders.

Once the editors are happy with the direction, every normative part will live in this repository, as CONTRIBUTING.md §3 requires; links to our repository will stay as background only.

**Questions for the editors.**

1. Is number 721 acceptable for the flagship, and may the drafts use "TAP-721" as the proposal name until a number is assigned? If not, how should the extension TAPs refer to the flagship before it has a number (currently `TAP-draft-netlist-bound-nft` in `requires`)?
2. Is the split right: core plus four in-document extensions, and three separate extension TAPs? In particular, should the TokenSet or Companion extension stand alone, or should Bridging stay inside the flagship?
3. The flagship's `requires` lists CAIP-19 and ERC-173. Are external non-EIP specifications acceptable in `requires`, and should they be pinned to a version?
4. Assets: the four drafts share one read-only chain snapshot (`assets/chain-snapshot.json`, BNB Smart Chain block 128,200,681). Should it be duplicated into each `assets/tap-…/` folder or kept as a shared file?
5. The PoD extension depends on a mining contract whose implementation source is not publicly verified. Does that block the Application type, or only Review?
6. Open questions already listed in the drafts that the editors may want settled early: a future `tapnet/2` with flattened REF records; a staged upload for netlist files above 49,152 bytes; a minimal lock-contract interface; a `vrf` seed source; and the verifier for the TAP-10 hub bridging profile.

🤖 Generated with [Claude Code](https://claude.com/claude-code)


