**Problem.** Courses, contests, hackathons and DAOs want to give TapeOut designers badges that record a skill, a result or a contribution together with the circuit behind it. Existing soulbound tokens carry no netlist and do not say what backs them: a badge minted after an automatic check, one vouched for by an organisation and one the holder minted about itself look the same in a wallet. Such badges are also easily presented as entitlements to rewards.

**Proposal.** A Standards TAP for non-transferable TAP-721 tokens (ERC-5192 locked, netlist bound at mint) with three kinds that tools must always label:

- **Proven**: minted by the contract when a submitted LATCH-free netlist with at most 16 inputs matches a specification committed on chain (truth-table hash, published work bounds so every check fits one transaction, commit-reveal per committer, an optional design key equivalent to the structural hash that rejects renamed copies);
- **Attested**: minted from an EIP-712 attestation by a named issuer (externally owned account or ERC-1271), with optional expiry and revocation;
- **Claimed**: minted by the holder about itself, optionally carrying Design Credits statements.

Every mint is sent or authorised by the recipient; holders can always renounce; lost keys are handled by re-issue with a link to the old token (for proven credentials after a delay with a veto), never by transfer. Interfaces `ITapCredential` (`0x5558759c`) and its Proven, Attested and Claimed extensions, a `tap.credential` metadata member, display rules, a neutral read-only query, and explicit non-claims: a credential confers no income, tokens, rewards or other payment, and its metadata must not suggest any.

**Type.** Standards.

**Builds on.** TAP-02, ERC-165, ERC-721, ERC-1271, ERC-5192, EIP-712, and the TAP-721 family (#66): the netlist-bound NFT draft (#67; credentials are L0 collections without a manifest) and the Design Credits draft (claim scopes and statements). A draft with vectors, a Python reference and a Solidity reference with Foundry tests is ready and will be submitted as `TAPs/TAP-draft-soulbound-credentials.md`.

**Number.** We ask the editors to consider number **5192**, as #66 did for 721: every credential contract implements ERC-5192 (minimal soulbound NFTs), and this TAP adds what ERC-5192 leaves open for netlist credentials. Until a number is assigned the draft is `TAP-draft-soulbound-credentials` with `tap: TBD`; the editors decide the final number.

