**Problem.** Netlists are public: anyone can tape out a netlist they did not design, two designers can reach the same netlist independently, and the account that tapes out a circuit may be a relayer, a wallet contract or a miner. Wallets, explorers and circuit tools nevertheless want to show "who made this". Today they either show nothing or present the minting account as the author, and there is no common way for a designer to sign a credit, record that one design derives from or optimizes another, or withdraw such a statement. Without one convention, a claim of authorship and a fact read from the chain end up looking the same.

**Proposal.** An Application TAP with two layers that tools must keep apart:

- **Facts** anyone can check against the chain: the *publication fact* of a circuit (the account its circuit token was minted to, with chain, processor, circuit id, block, transaction and log) with an exact verification procedure, and *earliest known occurrence* statements of a design (by netlist hash or structural hash) over a declared scope, refutable by an earlier verified occurrence.
- **Claims**: EIP-712 statements signed by an externally owned account or an ERC-1271 account, with a chain-agnostic domain: *Credit* (a role such as designer or optimizer, optional display name, design note and licence), *Lineage* (derivedFrom, supersedes, optimizes) and *Revocation*.
- A *credit bundle* that carries both, as a standalone file or as the `tap.credits` member of TAP-721 token metadata; an informative events-only anchor pattern; display rules (facts shown as verified only after verification, claims always shown as claims with their signer, conflicting claims side by side). The TAP grants no royalty, payment, exclusivity or identity verification.

A worked example on BNB Smart Chain (read-only reads pinned to one block, 4,248 circuits scanned) shows that the earliest occurrence of a well-known XOR design is not the reference circuit usually cited for it.

**Type.** Application.

**Builds on.** TAP-02, TAP-10, EIP-712, ERC-721, ERC-1271, and the TAP-721 family (#66): the netlist-bound NFT draft (#67) for `tap.credits` and the structural hash draft (#70) for design references. A draft with vectors and a dependency-free reference implementation is ready and will be submitted as `TAPs/TAP-draft-design-credits.md`; a Soulbound Netlist Credentials draft builds on it.

**Number.** We ask the editors to consider number **5375**, as #66 did for 721: ERC-5375 lets NFT authors give EIP-712 signed consent to being named, and states that consent is not proof of authorship; this TAP applies the same idea to TapeOut netlists and keeps such claims apart from on-chain facts. Until a number is assigned the draft is `TAP-draft-design-credits` with `tap: TBD`; the editors decide the final number.

