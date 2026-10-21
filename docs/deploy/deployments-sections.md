# Draft "Deployments" sections for the TAP-721 family

TAP-01 §7.2 item 9: a Standards TAP that depends on deployed contracts lists, for every chain, the addresses, the
implementation each proxy must point to, how anyone can recompute or verify these read-only, and whether each
upgrade path is sealed. None of the family's contracts is a proxy, so "implementation" is "n.a. (not a proxy)" and
"sealed" is answered by the contract's own freeze state. Replace `<ADDRESS>`, `<BLOCK>` and `<DATE>` from the
author's `deployments/<chainId>.json` and the editors' read-back (`docs/deploy/VERIFY.md`). Keep the sentence
"This TAP records deployments; it cannot order them" (TAP-01 §8) where a TAP already has it.

The family's TAPs today say "depends on no deployed contract". A test deployment does not change that: the
reference contracts remain reference implementations, deployed so that tools and editors can exercise them. The
drafts below say so explicitly, so that nobody reads a testnet address as "the" collection of the standard.

---

## TAP-721 Netlist-Bound NFTs (core)

```markdown
## Deployments

This TAP depends on no deployed contract of its own: any ERC-721 collection or companion that implements §8 is a
conforming deployment, and this TAP records none as canonical. Verifying a source (§3.2) uses the processor
factories and processor contracts that TAP-02 and TAP-10 list under their Deployments; on BNB Smart Chain the
processor factory is an upgradeable proxy that is not sealed (TAP-02, Deployments), so a verifier reads at a pinned
block and relies on the netlist hash fixed in the NFT, not on the factory's future behaviour.

**Reference deployment (testnet).** The reference implementation (`contracts/`, commit `<COMMIT>`) is deployed on
<CHAIN NAME> (chainId <CHAINID>) with the worked example of `assets/tap-draft-netlist-bound-nft/example`, so that
tools can be tested against a live collection. It is an example, not a collection of this standard; its images and
URIs point to `example.invalid`. Read back on <DATE> at block <BLOCK>, read-only, from two RPC operators
(`<RPC 1>`, `<RPC 2>`); every value matched.

| Contract | Address | Implementation it must point to | How to verify read-only | Sealed? |
|---|---|---|---|---|
| `TapNetlistVM` (library, linked) | `<ADDRESS>` | n.a. (not a proxy) | `cast code` equals `deployedBytecode` of `out/TapNetlistVM.sol/TapNetlistVM.json` built with `contracts/foundry.toml` (solc 0.8.28, 10,000 runs, `shanghai`, no metadata), apart from the library's own address in its call-protection prefix | immutable code, no owner |
| `TapNetlistNFT` (example collection, ERC-721 + §8) | `<ADDRESS>` | n.a. (not a proxy) | `supportsInterface` true for `0x80ac58cd`, `0x5b5e139f`, `0x49064906`, `0x282b67f6` (`ITapNetlistNFT`), `0xec7d7e20` (`ITapNetlistEval`), `0x3f7177c7` (`ITapNetlistTokenSet`); `manifestHash() = 0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983 = SHA-256(example/manifest.json)`; `masterSeed() = 0x000102…1f`; `tokenRange() = (1, 8)`; `pools()` roots `0x74db282d…e27a` and `0x376e16d7…08de` as in the manifest; for every token `netlistHashOf(t)` is one of the three example hashes and `netlistFile(h)` hashes to `h`; `entryIndexOf(t, i)` equals `tapnft.assignment` for chainId <CHAINID> and this address; code compared with a local build linked to the library above (`docs/deploy/VERIFY.md` §1) | **yes**: `frozen() = true`, `owner() = 0x0`; manifest, seed, pools and `tokenURI` can never change |
| `TapCompanion` (example companion for `ExampleLegacy721`) | `<ADDRESS>` | n.a. (not a proxy) | `collection() = <LEGACY ADDRESS>`; `supportsInterface` true for `0x282b67f6`, `0x12b40a6c` (`ITapCompanion`), `0x49064906`; same manifest, seed, roots and file checks as the collection; `endorsedBy() = <LEGACY OWNER>` = `owner()` of the legacy contract; `legacyUriFrozen() = true` | **yes**: `isSealed() = true`, `frozen() = true`, `owner() = 0x0` |
| `ExampleLegacy721` (test stand-in for a legacy ERC-721, `contracts/script/DeployCompanion.s.sol`) | `<ADDRESS>` | n.a. | `uriFrozen() = true`; `ownerOf(1..8)`; not part of the standard | URI frozen; `owner()` keeps `mint`, which the companion does not rely on |

Deployer `<DEPLOYER>` (a test account). Transactions: `contracts/broadcast/*/<CHAINID>/run-latest.json` at
commit `<COMMIT>`. No mainnet deployment exists. This TAP records deployments; it cannot order them.
```

## TAP-721 Netlist-NFT Bridging

```markdown
## Deployments

None of the contracts of this TAP is deployed, and no deployment is planned for TapeCode-Test1 v1. Each endpoint's
and adapter's owner is a constructor argument; until a pull request adds an address here, clients accept no
deployment as the official endpoints of TapeCode-Test1. The testnet deployment of the core reference collection
(TAP-721, Deployments) carries no gateway or mirror. This TAP records deployments; it cannot order them.
```

(n.a.: unchanged from the current text, plus the one sentence about the testnet deployment.)

## TAP-721 PoD attributes

```markdown
## Deployments

This TAP deploys no contract. It reads the processor contracts and the Netlist-Bound NFT getters
(`netlistHashOf`, `netlistFile`, `entryIndexOf`) of the collections it describes; the testnet reference collection
of TAP-721 (Deployments there) is one such collection and may be used to test a PoD reader:
`netlistOf(t)` returns a `tapnet/1` file whose header gives the NAND and LATCH counts that the example metadata
carries as `NAND` and `LATCH` attributes (`assets/tap-draft-netlist-bound-nft/example/token/<t>.json` for the
example's own assignment on chain 196; on another chain recompute the assignment first).
```

(n.a. for its own contracts; reads only.)

## TAP-721 Netlist structural hash

```markdown
## Deployments

This TAP depends on no deployed contract. The hash is computed off chain from a netlist file; the files stored by
the testnet reference collection of TAP-721 (`netlistFile(h)`) are inputs a tool can use to check its
implementation against the committed vectors (`assets/tap-draft-netlist-structural-hash/vectors.json`).
```

(n.a.)

## TAP-5192 Soulbound Credentials

```markdown
## Deployments

This TAP depends on no deployed contract. Anyone may deploy a credential contract; tools decide which contract code
they recognise (§10.1 item 4).

**Reference deployment (testnet).** The reference implementation
(`assets/tap-draft-soulbound-credentials/contracts`, commit `<COMMIT>`) is deployed on <CHAIN NAME> (chainId
<CHAINID>) so that wallets and tools can exercise ERC-5192 and the `ITapCredential*` interfaces. No credential was
issued by the deployment; specifications, attestations and claims are the author's or any user's to add. Read back
on <DATE> at block <BLOCK>, read-only.

| Contract | Address | Implementation it must point to | How to verify read-only | Sealed? |
|---|---|---|---|---|
| `SoulboundNetlistCredential` | `<ADDRESS>` | n.a. (not a proxy) | `supportsInterface` true for `0xb45a3c0e` (ERC-5192), `0x5558759c` (`ITapCredential`), `0x07aaf2dc` (Proven), `0x7587c9da` (Attested), `0x11e35684` (Claimed), `0x80ac58cd`, `0x5b5e139f`, and **false** for `0x49064906`; `REBIND_DELAY() = 604800`; `checkBounds() = (65536, 131072)`; `MAX_FILE_BYTES() = 49152`; `netlistFile(0xecb6f097…073e)` returns the `xor` file of `vectors.json`; `locked(t)` is true for every existing token and `transferFrom` always reverts; code equals a local build of the project (no library, no immutable) | no owner, no upgrade path: nothing to seal. The contract has no admin; the only time-bound power is a credential holder's 7-day rebind veto (§4.7) |

Deployer `<DEPLOYER>` (a test account). No mainnet deployment exists. This TAP records deployments; it cannot order them.
```

## TAP-7007 Large Netlists and Verifiable Execution

The TAP-7007 repository (`tap-large-netlists`) has the same package; its draft section is
`docs/deploy/deployments-sections.md` there. Summary of what it lists: `TapLargeNetlistStoreOwned` (chunk oracle;
`supportsInterface(0x8230af7f)` for `ITapLargeNetlistStore`, `largeInfo`/`largeStored`/`largeChunk` of the two
example files, `largeChunkPointer` code hashes), `TapLargeVerifier` (`segmentBudget() = (6000, 256, 16)`,
`store()`, the selectors `verifySegment` `0xaca8e751`, `verifyBeatEnd` `0x364abc73`), `TapLargeGameLib` (external
library) and the informative `TapLargeDisputeGame` (immutable parameters). None is a proxy; the verifier and the
library are stateless; the game's parameters are immutable; the store's only power is `addKnown` by its owner, which
adds hashes and can remove nothing.
