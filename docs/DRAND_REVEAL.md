# drand reveal for TAP-721 collections

This guide covers the drand reveal kit in `contracts/src/tools/drand/`: `TapDrandReveal`, a controller for the
reference collection `TapNetlistNFT` that writes the master seed only as the drand quicknet randomness of one round R and
stops all minting before that round can be known by its clock; `TapDrandRevealFactory`, which creates controllers; and
`DrandBeacon`, the ownerless contract that checks a round's BLS signature on chain. It also lists the checks a reader can
make by hand.

Status: the code and its Foundry tests are in this repository. **Nothing is deployed on any chain by this repository,
and neither the kit nor the reference contracts have had an external audit** (see [SECURITY.md](SECURITY.md)).

| Path | Content |
|---|---|
| `contracts/src/tools/drand/TapDrandReveal.sol` | The controller (344 lines) |
| `contracts/src/tools/drand/ITapDrandReveal.sol` | Its interface, events and errors, plus the beacon and collection functions it uses |
| `contracts/src/tools/drand/TapDrandRevealFactory.sol` | Creates controllers and records which controller made which collection |
| `contracts/src/tools/drand/DrandBeacon.sol` | Ownerless quicknet BLS verifier and round cache (EIP-2537), shared by every collection |
| `contracts/test/tools/drand/` | The tests (section 10); `mocks/` holds a beacon stand-in and a crafted collection |
| `contracts/test/fixtures/drand-quicknet-rounds.json`, `fetch_drand_rounds.py` | 49 real quicknet rounds, each taken from two relays; the script that records them |
| `contracts/test/fixtures/drand-beacon-code.json`, `make_drand_beacon_code.py` | The canonical beacon runtime and its generator |

Section numbers (§) refer to `TAPs/TAP-draft-netlist-bound-nft.md`. Section 7 lists the checks a reader can make by
hand. A static checker page can follow as a separate PR.

## 1. The problem

The reference `TapNetlistNFT` trusts its owner. The owner can:

- call `reveal(bytes32 seed)` with any non-zero value, and so pick which token receives which pool entry;
- mint, or let minters set with `setMinter` mint, at any time until the reveal, including after the drand round is
  public, when anyone can compute which unminted id receives which entry;
- schedule a blockhash reveal instead. The block producer chooses block hashes, and on single-sequencer chains such as
  X Layer that is one party (§6.1 item 6);
- use the other commit variants, and transfer ownership.

§6.1 says that the manifest fixes the drand round before the seed can be known (item 1), and that minting SHOULD finish
before the seed is known (item 4). It leaves "how the master seed is written on chain" to the implementation (item 8). A
tool can show afterwards that `masterSeed()` differs from the round's randomness, or that a mint came after the round,
but by then the damage is done. With the reference contract alone, both rules are promises.

## 2. What the kit enforces

- **Construction.** `factory.create` deploys a `TapDrandReveal`. Its constructor deploys the collection with `CREATE`
  and passes itself as `initialOwner`. With the reference initcode, the collection never has another owner (after the
  freeze it has none), and it never has a minter. The constructor does not verify the initcode (see the limits below).
- **Surface.** The controller has no code path to `setMinter`, `transferOwnership`, `commitManifestNoReveal`,
  `commitManifestTokenSet` or `scheduleBlockhashReveal`. Its runtime contains no `DELEGATECALL`, `CALLCODE`,
  `SELFDESTRUCT`, `CREATE` or `CREATE2`. It has no payable function and no upgrade path. Because the controller is the
  owner, `revealFromBlockhash` (permissionless in the reference) reverts for every block: it needs a block the owner
  scheduled.
- **Clock.** `clock() = max(block.timestamp + lagAtCommit, quicknetTime(beacon.latestVerifiedRound()))`. `lagAtCommit`
  is stored at the commit: `max(0, t(selfTestRound) − block.timestamp)`. A signed round cannot come from the future, so a
  self-test round ahead of the block proves the chain clock trails real time by at least that much, and the controller
  counts that lag from then on. A round posted to the beacon only moves the clock forward.
- **One round.** R is fixed once:
  - fixed mode, at the commit: the round in the manifest, with `R > roundAt(clock() + MIN_FIXED_LEAD)` (13 h) and
    `t(R) ≤ clock() + MAX_FIXED_LEAD` (365 days);
  - deferred mode, by `scheduleReveal()` once minting is over: `R = scheduleRound() = roundAt(clock() + scheduleDelay) + 1`.
    `scheduleDelay` is an immutable constructor argument between `MIN_SCHEDULE_DELAY` (1 h) and `MAX_SCHEDULE_DELAY`
    (7 days); the constructor reverts `BadDelay` outside that range, also in fixed mode, which never reads it.
- **Minting gate.** `TapDrandReveal.mint(to, tokenId)` uses the same selector as the reference `mint`. It accepts only
  allowed minters, and only while `mintOpen()` is true: committed, not closed, not revealed, `minted < supply`, and
  either R unset or `R ≥ earliestRound() = roundAt(clock() + REVEAL_DELAY) + 1`. `REVEAL_DELAY` (10 min) is only this
  fixed-mode gateway cutoff: in deferred mode R is unset while minting is open.
- **The seed.** `revealDrand(signature)` writes `DrandBeacon.verify(R, signature)`, which is SHA-256 of the signature
  after a BLS check against quicknet's public key. Anyone may call it. The caller chooses only when the seed is written,
  not its value.
- **Self-test.** At the commit the beacon must accept a quicknet signature at most one day old (by chain time) and reject
  the same bytes with the sort flag flipped. This rules out a verifier that would give a round two randomness values. The
  round and its bytes are stored for the emergency path, and the round sets `lagAtCommit`.
- **Emergency path.** `revealUnverified` (admin only) opens only if all of these hold: 72 h have passed since R, R is
  not cached in the beacon, and the beacon now fails the self-test it passed at the commit. See §5, step 12.

### Who may call what

| Function | Caller | When |
|---|---|---|
| `allowMinter(account, allowed)` | admin | any time; a minter can mint only while `mintOpen()` |
| `commit(...)` | admin | once |
| `mint(to, tokenId)` | allowed minters | while `mintOpen()` |
| `closeMint()` | admin or a minter | after the commit, before a close or the reveal |
| `scheduleReveal()` | admin; anyone from `closedAt + 1 day` | deferred mode, once, after minting is closed |
| `revealDrand(signature)` | anyone | once R's signature exists |
| `setBaseURI(uri)` | admin | until frozen |
| `freeze()` | admin | after the reveal; it ends every controller power over the collection |
| `revealUnverified(signature)` | admin | emergency only (step 12) |

The admin and `scheduleDelay` are immutable constructor arguments, and nothing can change them later. Use a multisig for
the admin.

### The guarantee

Take a collection whose construction is proven (section 7) and whose seed was written by `revealDrand`. For it:

1. `masterSeed()` is the randomness of quicknet round R, and the beacon checked R's BLS signature on chain;
2. when R was fixed, its production time lay more than `MIN_FIXED_LEAD` (fixed mode) or `scheduleDelay` (deferred mode)
   after the controller's clock;
3. every token was minted through the gateway, in fixed mode while the controller's clock was more than `REVEAL_DELAY`
   before R, in deferred mode before R was fixed;
4. nobody, the deployer and the admin included, could write another value or a second seed. Within the clock condition
   below, the admin chose at most when things happened (which future round in fixed mode, when to schedule in deferred
   mode), never the value.

Items 2 and 3 are stated against the controller's clock. They hold against real time as long as the chain clock does not
trail real time by more than the margins in the next section.

### Limits of the guarantee

- **drand.** quicknet is a threshold network run by the League of Entropy. If enough of its nodes colluded, they could
  compute a round's signature early and pass it on. The kit cannot detect this. If quicknet stops producing rounds, R
  never arrives and the collection stays unrevealed: there is no fallback source.
- **Chain clock.** The controller knows the time only from block timestamps, the lag its commit proved, and the newest
  round posted to the beacon. No on-chain clock removes the following, and chain data cannot show it:
  - **deferred mode:** if the chain clock trails real time by more than `scheduleDelay` when R is scheduled (a sequencer
    stall followed by catch-up blocks) and no real-time round has been posted to the beacon, R may already be public
    when it is fixed. The scheduler (the admin, or anyone from `closedAt + 1 day`) can then post an older round that looks
    fresh by the chain clock and pick among the blocks of that window, that is among rounds already public, so the seed
    is no longer independent of the scheduler. `scheduleDelay` sets how long such a stall must be; a keeper that posts
    the newest round to the beacon every minute pins `clock()` to real time while it runs. The test
    `test_lag_deferredResidualAndItsMitigation` demonstrates the residual and the effect of posting a round first;
  - **fixed mode, at the commit:** a chain clock that trails real time by more than `MIN_FIXED_LEAD` (13 h, above the
    12 h OP Stack sequencing window), with no real-time round in the beacon, lets the admin commit an already-public R;
  - **fixed mode, after the commit:** a chain clock that falls more than `REVEAL_DELAY` further behind real time than
    `lagAtCommit`, with no real-time round posted, leaves the gateway open after R is public. Late mints can then target
    known entries; the seed itself stays R's. Anyone can close the gap at any time with
    `DrandBeacon.verify(latestRound, signature)`. A block producer that both holds timestamps back and censors those
    posts can defeat the guard.
- **Verifier failure.** If the chain removes or reprices the EIP-2537 precompiles, the beacon can fail its self-test. From
  72 h after R the admin may then write SHA-256 of any 48 bytes whose first byte carries a compressed-G1 flag (`0x80` or
  `0xa0` in the top three bits). The bytes are published in the event, so the misuse can be detected but no longer
  prevented. While the beacon passes its self-test, the path reverts `VerifierWorks`. If anyone cached R in the beacon
  before the failure, `revealDrand` keeps working (a cached round is compared by SHA-256 only) and the emergency path
  stays closed (`RoundCached`).
- **Admin liveness.** In deferred mode, R is fixed only after minting closes: on a sell-out, or by `closeMint()` from
  the admin or a minter. An admin who never closes delays the reveal indefinitely, but cannot choose the seed. If the
  admin key is lost, `revealDrand` still works for anyone, and so does `scheduleReveal` from `closedAt + 1 day`.
  Minting can then still close on a sell-out or through a minter's `closeMint()`. `allowMinter`, `setBaseURI`, `freeze`
  and the emergency path are lost. In fixed mode nothing before the reveal needs the admin.
- **Construction is proven off chain.** The constructor accepts any initcode whose `owner()` returns the controller, and
  the factory accepts any initcode. `factory.controllerOf(collection)` and the `Created` event are provenance: they say
  this factory built this controller with this (unchecked) initcode. A crafted initcode passed through the real factory
  can plant a minter or a hidden owner path while deploying a byte-identical reference runtime and passing every on-chain
  check (`test_craftedInitcodeIsAcceptedOnChainButItsHashDiffers`). The proof is the comparison of
  `collectionInitCodeHash()` (also in `Created`) and the collection runtime with a reference build (section 7.1). Do not
  treat a collection as a kit collection without it, and do not let an indexer or marketplace rely on `controllerOf` alone.

## 3. Parts and addresses

The shared pieces are created through the deterministic deployer (Arachnid, `0x4e59b44847b379578588920cA78FbF26c0B4956C`,
runtime keccak `0x2fa86add…7e4989`) with salt 0, so they have the same address on every chain that has it. The build
recipe is this repository's: solc `0.8.28`, optimizer 10,000 runs, EVM `shanghai`, `bytecode_hash = "none"`,
`cbor_metadata = false` (`contracts/foundry.toml`). The bytes do not depend on file names or import paths.

| Piece | Address | Hashes |
|---|---|---|
| `TapNetlistVM` (library of the reference collection) | `0x82aF8337aa103e35b4A9C6cF11195E36E77Fa036` | initcode `0xcffcf55318d77d492dc26abdc3d28274a62860d59e2ffb886878eface8f2aac9` |
| `DrandBeacon` | `0x777D3Ece3CB4E7D3782Da938CbCf8c2c8AcE55Ca` | initcode `0x815fdcaf3572e2e7272a212e34c6e6df32ebd68775228c35402ebb9a5ec564f5`, runtime `0x5af33305a251aaeff7728080afdf2cdf71d97395115d0a4faa98dd8c9f951fe9` |
| `TapDrandRevealFactory` | `0x1cE83c28a85574f9E16032B8B5f14794a9312f4B` | initcode `0x31a39fa170899453db448f80241eeac0da2730cb919a42807058481dd4c4e5de`, runtime `0x8910380b54a0f2057836bebd6a496fbeef1f27921feb725b2dfa5a17de66dc80` |

Each collection also has its own pieces:

| Piece | Address | Note |
|---|---|---|
| `TapDrandReveal` | `CREATE(factory, n)` | Creation code `0x98eea72e…9a464ac`. Immutables: `collection`, `admin`, `scheduleDelay`, `collectionInitCodeHash` (19 byte ranges in the runtime). Runtime with the immutables zeroed: keccak `0xce064e712ea7e2701cb51615240eb3ed9e42be291b7724a140cdd7f2b8920cd1`, 12,834 bytes. |
| `TapNetlistNFT` | `CREATE(controller, 1)` | The reference collection, linked to the VM above. Initcode keccak (without constructor arguments) `0x5f3a1464d0c3400e402b50a15641848d08428edb741c690c517cadffb2da12ec`, runtime keccak `0x5e5920740042fabf31851307d510b67e7ba34dbf2e46c6e9ce55695648f80b69`, 23,815 bytes. |

`TapDrandReveal` pins the beacon as the constants `DRAND_BEACON` and `DRAND_BEACON_CODEHASH`; `factory.create` reverts
`BadBeacon` unless that code is at that address.

Nothing is deployed by this repository. `contracts/test/tools/drand/DrandCanonical.t.sol` pins every bytecode hash and
the two CREATE2 addresses, the VM and the linked reference collection (`test_referenceCollectionHashes`), deploys the
beacon and the factory through a copy of the deterministic deployer, and creates a collection through the factory with
the real reference initcode. The artifacts of `forge build` with the native solc 0.8.28 are also byte-identical to an
independent build of the same sources (solc-js 0.8.28, same settings): creation and runtime code of the three
contracts, the controller's 19 immutable ranges, `TapNetlistVM`, and `TapNetlistNFT` with the VM linked. To reproduce a
hash by hand:

```sh
cd contracts && forge build
cast keccak $(forge inspect DrandBeacon bytecode)                 # 0x815fdcaf…ec564f5
cast keccak $(forge inspect DrandBeacon deployedBytecode)         # 0x5af33305…f951fe9
cast keccak $(forge inspect TapDrandRevealFactory bytecode)       # 0x31a39fa1…c4e5de
cast create2 --deployer 0x4e59b44847b379578588920cA78FbF26c0B4956C --salt 0x0000000000000000000000000000000000000000000000000000000000000000 \
  --init-code-hash 0x815fdcaf3572e2e7272a212e34c6e6df32ebd68775228c35402ebb9a5ec564f5   # 0x777D…55Ca
```

The chain must have:

- the EIP-2537 precompiles, which the beacon calls at `0x0b` (G1ADD), `0x0f` (pairing) and `0x10` (MAP_FP_TO_G1),
  besides modexp at `0x05`. Check this on the target chain before relying on the kit: the commit's self-test fails
  (`SelfTestFailed`) where they are missing, and without them the beacon never accepts a signature;
- the deterministic deployer;
- a transaction gas limit of at least about 9M for `factory.create` with the reference initcode: 8.1M of execution plus the calldata (section 8).

## 4. Fixed or deferred mode

| | Fixed | Deferred |
|---|---|---|
| Manifest `reveal.round` | R | `0`, with the rule in `tapDrandReveal` |
| R fixed | at the commit, chosen by the admin, more than 13 h (`MIN_FIXED_LEAD`) and at most 365 days ahead of `clock()` | by `scheduleReveal()` after minting closed: `R = roundAt(clock() + scheduleDelay) + 1` |
| Minting ends | when `clock()` reaches about `t(R) − 600`, or earlier on a sell-out or `closeMint()` | on a sell-out or `closeMint()` |
| Residual under an unseen chain-clock lag | a lag over 13 h at the commit; a further lag over 10 min before R (late mints) | a lag over `scheduleDelay` at scheduling, with no real-time round posted |
| TAP-721 §6.1 | conforms: the manifest names R | does not conform: the manifest has `round: 0`, which is not a quicknet round |
| Who must act before the reveal | nobody | the admin or a minter closes, unless sold out; the admin schedules (anyone can, from 1 day after the close) |
| Use when | the end of the sale is known at least 13 h ahead | the length of the sale is not known |

Fixed mode is the conformant one. In deferred mode the manifest names no quicknet round, so a tool that follows §6.1
fails on it: `tools/collection/verify_collection.py` stops in `drand.round_time`, which rejects rounds below 1. Deferred
mode needs a change to the draft. A minimal one: allow `reveal.round = 0` when the manifest also carries a `rule` that
defines R from on-chain data (here the block of `scheduleReveal()`), and let tools read R from the `RevealScheduled`
event of the controller named in the manifest. Until the draft says so, deferred mode is outside the standard. The
deferred-mode code can be split out of this change if the maintainers prefer.

## 5. Deploy and wire, step by step

**1. Build** the VM, the beacon, the factory and the reference `TapNetlistNFT` with `forge build`. Compare every
initcode hash and CREATE2 address with section 3. If anything differs, the code is different: stop.

**2. Shared contracts**, once per chain. Skip any that already have code. Anyone may deploy them; each is a transaction
to `0x4e59…956C` with data = 32 zero bytes (the salt) followed by the initcode. Deploy in this order: VM, beacon,
factory. `factory.create` reverts `BadBeacon` unless the pinned beacon code is at `0x777D…55Ca`. Afterwards, check
`keccak256(eth_getCode)` of each one against section 3.

**3. Collection initcode.** Take the reference `TapNetlistNFT` initcode (`forge inspect TapNetlistNFT bytecode`, 24,704
bytes) and write the VM address into its four library link slots, at byte offsets 5,246, 5,987, 7,399 and 10,066 (20
bytes each, zero in the unlinked output). Do not append constructor arguments: the controller appends
`abi.encode(name, symbol, baseURI, controller)` itself. A collection built from any other recipe fails the comparison of
section 7.1.

**4. Create.** Call:

```
factory.create(admin, scheduleDelay, collectionInitCode, name, symbol, baseURI)
```

`scheduleDelay` is in seconds, from 3,600 (1 h) to 604,800 (7 days); pass 3,600 in fixed mode, which never reads it.
In deferred mode, pick it above the longest chain-clock stall you accept (section 2, limits). Anyone may send this
transaction. The event `Created(controller, collection, admin, collectionInitCodeHash)` gives the two addresses, and
`controller.scheduleDelay()` the delay. Before announcing anything, make the construction checks of section 7.1.

**5. Manifest** (§5). Write the manifest only now, because it must name the collection and the controller:

- `collection`: `chainId`, `address` (lowercase), `firstTokenId` and `supply`. Only range mode is supported, and the
  reference caps `supply` at 100,000;
- `pools`: one or two;
- the `reveal` object and the `tapDrandReveal` member of section 6.

Keep the bytes ASCII-only, publish them at their URIs (§4.2), and take `manifestHash = SHA-256(bytes)`. In fixed mode,
choose R now (step 7 gives the rule).

**6. Sale contract.** Point the sale at the controller instead of the collection. The sale calls
`controller.mint(to, tokenId)`, with the reference selector, and should expect the revert `MintingClosed`. The controller
also answers `manifestHash()`, so a sale that reads it from "the NFT" works unchanged. A sale may call
`controller.closeMint()` when it ends. Then the admin calls `allowMinter(sale, true)`.

The admin has no mint right of its own. To mint team tokens, allow a team minter and mint before the close; those mints
are as blind as everyone else's.

**7. Commit.** Fetch a recent quicknet round together with its signature, at most one day old by chain time:
`https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/latest`. Then the admin
calls:

```
commit(manifestHash, firstTokenId, supply, pools, round, selfTestRound, selfTestSig)
```

- `pools` are `(label, fields, root)` with field mask `image = 1`, `netlist = 2`, both `3`, as in the manifest;
- `round` is R in fixed mode, `0` in deferred mode;
- `selfTestSig` is the 48-byte signature, passed as `bytes`.

The commit uses about 0.73M gas in the tests (section 8). It forwards `commitManifest` (the reference emits
`ManifestCommitted`) and emits `Committed`, plus `RevealScheduled` in fixed mode. It stores
`lagAtCommit = max(0, t(selfTestRound) − block.timestamp)`. It reverts:

- `SelfTestFailed` when the beacon rejects the round, accepts its sort-flipped copy, or the round is more than a day
  older than the block. If a fresh round fails, the kit does not work on that chain;
- `BadRound` (fixed mode) unless, at the commit block, with
  `clock = max(block.timestamp + lagAtCommit, t(beacon.latestVerifiedRound()))`,
  `R > roundAt(clock + 46,800)` and `t(R) ≤ clock + 365 days`.

Here `t(r) = 1692803367 + 3·(r − 1)` for `r ≥ 1` (`t(0)` is the genesis time, 1692803367) and
`roundAt(t) = floor((t − 1692803367) / 3) + 1`, as in `DrandBeacon`. R is part of the manifest, so an R that turns out
too early means a new manifest. Leave margin above 13 h: in fixed mode the gateway closes at about `t(R) − 600` whatever
the state of the sale. A self-test round taken right before sending gives `lagAtCommit` of 0 to a few seconds on a chain
that keeps time.

**8. Sale.** Minting runs through the gateway. `mintOpen()`, `minted()` and `lastMintAt()` show the state.

**9. Close and fix R.**

- **Fixed mode.** Nothing is required. The gateway closes by time and `closedAt` stays 0; `closeMint()` can close it
  earlier. If the chain clock may lag, have someone post fresh rounds to the beacon in the last hour before
  `t(R) − 600`. Anyone can post a round with `DrandBeacon.verify(round, signature)`, with a gas limit of about 600k.
- **Deferred mode.** Selling the last id closes minting. Otherwise the admin or a minter calls `closeMint()`. Then call
  `scheduleReveal()`: the admin may do so any time after the close, anyone from `closedAt + 1 day`. Send it in one
  batch, right after `DrandBeacon.verify(latestRound, signature)`, so that R is computed from a fresh drand time. R is
  then `scheduleRound() = roundAt(max(block.timestamp + lagAtCommit, t(newest)) + scheduleDelay) + 1`, a round produced
  `scheduleDelay` to `scheduleDelay + 3 s` later, and `RevealScheduled(R, t(R), newest)` records it. Compare the chain
  clock with real time before you send.

**10. Reveal.** At or after `t(R)`, take R's signature from a relay. Anyone then calls `revealDrand(signature)`, with a
gas limit of at least 600k. A second call reverts `AlreadyRevealed`, so it does not matter who sends it first. The
reference emits `Revealed(seed)`, and the controller emits `RevealedVerified(R, seed, caller)`. From `t(R)` onwards
anyone can compute every assignment, so warn holders in advance and publish the revealed metadata promptly (§6.1 item 5).

**11. After the reveal.** The reference functions `loadPool` / `loadPoolChunk` (available from the commit), `bind`,
`storeNetlist` and `markKnown` are open to anyone, and the freeze does not affect them. The kit does not touch them.
The admin sets the final base URI with `setBaseURI`, then calls `freeze()`. The freeze cannot be undone: `owner()`
becomes 0, and every power the controller forwards ends.

**12. Emergency path.** Use it only when `revealDrand` cannot work. All of the following must hold:

- R is fixed and not yet revealed;
- `block.timestamp ≥ t(R) + 72 h`;
- `beacon.randomnessOf(R) == 0`;
- `verifierWorks()` is false. Check it by `eth_call` with at least 2.2M gas, because with less it reverts `GasTooLow`.

The admin then calls `revealUnverified(signature)` with R's real 48 bytes, the same from two relays, and a gas limit of
2.2M or more. It raises `GasTooLow` whenever less than `SELFTEST_GAS + SELFTEST_GAS / 63 + 50,000` (2,081,746) gas is
left at the self-test, so the self-test cannot be starved into failing. The seed is SHA-256 of the bytes,
`verifiedOnChain()` stays false, and `RevealedUnverified(R, bytes, seed)` publishes the bytes for checkers.

## 6. The manifest reveal object

Fixed mode (the round is an example):

```json
"reveal": {
  "source": "drand",
  "chainHash": "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971",
  "round": 34000000
},
"tapDrandReveal": {
  "v": 1,
  "mode": "fixed",
  "factory": "0x1ce83c28a85574f9e16032b8b5f14794a9312f4b",
  "controller": "0x<controller, lowercase>",
  "revealDelaySeconds": 600,
  "minFixedLeadSeconds": 46800
}
```

Deferred mode (with `scheduleDelay` = 3600). This form is not valid under §6.1 as written (section 4):

```json
"reveal": {
  "source": "drand",
  "chainHash": "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971",
  "round": 0
},
"tapDrandReveal": {
  "v": 1,
  "mode": "deferred",
  "factory": "0x1ce83c28a85574f9e16032b8b5f14794a9312f4b",
  "controller": "0x<controller, lowercase>",
  "revealDelaySeconds": 600,
  "scheduleDelaySeconds": 3600,
  "rule": "R = roundAt(max(t + lagAtCommit, tNewest) + 3600) + 1, t = timestamp of the block of scheduleReveal(), tNewest = production time of the newest round verified in the beacon then; scheduleReveal only after minting is closed"
}
```

`tapDrandReveal` is a convention of the kit, not of the draft: a top-level member of the manifest. §5.1 tells tools to
ignore members they do not know. A reader checks that `reveal.source = "drand"` with exactly quicknet's `chainHash`
(64 lowercase hex digits, no `0x`); that in fixed mode `reveal.round` equals the controller's `revealRound()`; that in
deferred mode `reveal.round = 0`, `mode = "deferred"` and `scheduleDelaySeconds` equals `scheduleDelay()`; and that
`factory` is the pinned factory and `revealDelaySeconds` equals `REVEAL_DELAY()` (600). The manifest hash covers the raw
bytes (§5.1): a tool that re-serializes the JSON gets another hash.

## 7. Verifying a reveal

### 7.1 By hand

The commands use Foundry `cast` and `curl`. Set:

```sh
RPC=https://rpc.xlayer.tech
COLL=0x...                                      # the collection
FACTORY=0x1cE83c28a85574f9E16032B8B5f14794a9312f4B
BEACON=0x777D3Ece3CB4E7D3782Da938CbCf8c2c8AcE55Ca
QN=52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971
```

1. **Construction.**

   ```sh
   CTRL=$(cast call $FACTORY "controllerOf(address)(address)" $COLL --rpc-url $RPC)   # 0x0: not a kit collection
   cast keccak $(cast code $FACTORY --rpc-url $RPC)       # 0x8910380b…de66dc80
   cast compute-address --nonce 1 $CTRL                   # must be $COLL
   cast call $CTRL "collectionInitCodeHash()(bytes32)" --rpc-url $RPC
   cast keccak $(cast code $COLL --rpc-url $RPC)
   cast keccak $(cast code $BEACON --rpc-url $RPC)        # 0x5af33305…f951fe9
   cast call $COLL "owner()(address)" --rpc-url $RPC      # $CTRL, or 0 once frozen()
   cast call $COLL "isMinter(address)(bool)" $CTRL --rpc-url $RPC    # false
   ```

   `controllerOf` only says which controller this factory built; it is not proof. With the canonical VM linked, the
   initcode hash and the collection runtime keccak must be the pair of section 3 (`0x5f3a1464…da12ec` /
   `0x5e592074…f80b69`). For any other VM, link your own build of the reference to the VM address found in the
   collection runtime, compare the hashes, and check that the VM's runtime is the reference library.

   The initcode hash is the check that decides. A crafted constructor can plant a minter and still deploy a runtime
   that is byte-identical to the reference, so a matching runtime alone proves nothing.

2. **Manifest.** Download it and compare its hash with the chain:

   ```sh
   sha256sum manifest.json
   cast call $COLL "manifestHash()(bytes32)" --rpc-url $RPC
   ```

   Check the section 6 fields.

3. **Timeline.** Read `revealRound()`, `fixedRound()`, `committedAt()`, `lagAtCommit()`, `selfTestRound()`,
   `lastMintAt()`, `closedAt()`, `scheduledAt()`, `newestRoundAtSchedule()`, `scheduleDelay()` and `verifiedOnChain()`
   from `$CTRL`. With `t(r)` and `roundAt(t)` from step 7 of section 5, and
   `clk = max(scheduledAt + lagAtCommit, t(newestRoundAtSchedule))` (use `scheduledAt + lagAtCommit` alone when
   `newestRoundAtSchedule` is 0):
   - `committedAt < t(R)`, and `lastMintAt + 600 < t(R)`;
   - fixed mode: `R ≥ roundAt(clk + 46800) + 1`. `t(R) − clk` is how far a chain-clock lag at the commit would have had
     to go before R could be public;
   - deferred mode: `lastMintAt ≤ closedAt ≤ scheduledAt`, and `R = roundAt(clk + scheduleDelay) + 1`;
   - `lagAtCommit` and `t(selfTestRound) − committedAt` near 0. A larger value means the chain was lagging at the commit;
     the controller counts it from then on. A value near 0 is only a lower bound: the admin picks the self-test round, so
     an admin can record 0 during a real lag;
   - `scheduledAt + lagAtCommit − t(newestRoundAtSchedule) ≤ 60`, with `newestRoundAtSchedule` not 0, shows that a
     round was posted around scheduling. It does not show that the round was fresh in real time: both values come from
     the chain (section 2, limits).

4. **drand.** Fetch round R from two independent relays:

   ```sh
   curl -s https://api.drand.sh/$QN/public/$R
   curl -s https://drand.cloudflare.com/$QN/public/$R
   echo -n <signature> | xxd -r -p | sha256sum            # must equal "randomness"
   ```

   The two signatures must be equal. Each relay's `/$QN/info` must hash to `$QN`:
   SHA-256(u32be(period) ‖ i64be(genesis_time) ‖ public_key ‖ groupHash ‖ "quicknet"). `fetch_drand_rounds.py` does these
   checks for the recorded test rounds.

5. **Seed.** `cast call $COLL "masterSeed()(bytes32)"` must equal `0x` + randomness. If `verifiedOnChain()` is true, the
   beacon checked the BLS signature during `revealDrand`, and `cast call $BEACON "randomnessOf(uint64)(bytes32)" $R`
   returns the same value. To check the BLS signature yourself, run
   `cast call $BEACON "check(uint64,bytes)(bool,bytes32)" $R 0x<signature> --gas-limit 5000000`. If it returns false
   after an emergency reveal, read `cast call $CTRL "verifierWorks()(bool)" --gas-limit 3000000`: false means the chain
   no longer verifies BLS, and the relays' agreement is what is left.

6. **Assignments.** Run Python in `assets/tap-draft-netlist-bound-nft/`:

   ```python
   import tapnft
   m = tapnft.check_manifest(open("manifest.json", "rb").read())
   seed = bytes.fromhex("<masterSeed without 0x>")
   print(tapnft.assignment(m, seed, 1))   # {pool label: entry index} for token 1
   ```

   Compare the result with `cast call $COLL "entryIndexOf(uint256,uint256)(uint256)" 1 <poolIndex>`.

## 8. Gas and sizes

Execution gas measured by the Foundry tests (`forge test --hardfork prague --match-path "test/tools/drand/*" -vv`; the
figures are printed by `test_gas_*`, `test_cachePath`, `test_gasOfAFirstVerification`, `test_fixedMode_endToEnd` and
`test_fixedMode_revealWhenRIsAlreadyCached`). They do not include the 21,000 base cost or calldata, and a first access
to an account or a slot is cold. Calls that carry a drand signature move by some tens of gas with the bytes of the round.

| Call | Gas |
|---|---|
| `factory.create` (reference initcode) | 8,113,742 |
| `commit` (real self-test) | 729,359 |
| `scheduleReveal` | 42,919 |
| `revealDrand`, R not yet in the beacon | 344,775 |
| `revealDrand`, R already cached | 155,554 |
| `DrandBeacon.verify`, a new round / a cached round | 218,553 to 225,140 / 28,684 |
| `DrandBeacon.check` | 147,307 |
| `mint`, direct by the reference owner, 1st / 2nd token | 86,599 / 67,499 |
| `mint` through the gateway, fixed mode, 1st / 2nd | 110,263 / 89,163 |
| `mint` through the gateway, deferred mode, 1st / 2nd | 98,766 / 81,666 |
| Gateway overhead per mint (2nd token), fixed / deferred | 21,664 / 14,167 |

Fixed mode costs more per mint because the time guard reads the beacon (`latestVerifiedRound`, `quicknetTime`,
`roundAt`) on every mint. `factory.create` stays under the 16,777,216 gas cap of EIP-7825. The beacon calls its
precompiles with gas caps well above both price schedules a chain may run (modexp under EIP-2565 and EIP-7883 among
them) because the contract is immutable.

Sizes in bytes (runtime / initcode):

| Contract | Runtime | Initcode |
|---|---|---|
| `TapDrandReveal` | 12,834 | 14,309 |
| `TapDrandRevealFactory` | 15,726 | 15,754 |
| `DrandBeacon` | 5,841 | 5,869 |
| `TapNetlistNFT` (reference) | 23,815 | 24,704 |
| `TapNetlistVM` | 2,554 | 2,606 |

All stay under EIP-170 (24,576) and EIP-3860 (49,152). `factory.create` carries the reference initcode in its calldata.

## 9. What is not covered

- Token-set mode, no-reveal collections, `TapCompanion`, `TapMintBoundNFT`, existing ERC-721 contracts and L0
  collections. The controller forwards range-mode `commitManifest` only.
- Collections that already exist. The kit must create the collection, so a deployed collection cannot be moved under
  it.
- Other drand chains and other sources: the beacon pins quicknet's public key.
- Chains without EIP-2537.
- Off-chain content: metadata, images and manifest hosting. Until the freeze, the admin can change `tokenURI` with
  `setBaseURI`; a swap is detectable under §7.3, but not prevented.
- The sale: price, limits, bots, refunds and funds. The controller holds no funds. It only controls when minting is
  possible.
- Trading between `t(R)` and the published metadata: anyone can compute the assignments as soon as R is out.
- A chain clock lagging real time beyond the margins of section 2. No on-chain clock removes those residuals; the
  tests state the margin they assume.
- More than 100,000 tokens, the reference limit.
- External audit: neither the kit nor the reference contracts have had one.

## 10. Tests

```sh
cd contracts
forge build && forge test                                              # default: shanghai, as in CI
forge test --hardfork prague --match-path "test/tools/drand/*"         # runtime Prague, canonical bytes
forge test --evm-version prague --match-path "test/tools/drand/*"      # compiled for Prague too
python3 test/fixtures/fetch_drand_rounds.py --check                    # network: the fixture still matches two relays
python3 test/fixtures/make_drand_beacon_code.py --check                # the recorded beacon runtime is the compiled one
```

The beacon needs EIP-2537, which `shanghai` does not have, so every test that verifies a BLS signature skips itself
(reported as skipped, not as passed) on such an EVM. The default `forge test` therefore runs the controller and factory
suites on a beacon stand-in, the fail-closed tests (without the precompiles a real signature must never verify) and the
byte-for-byte pins (7 tests). With `--hardfork prague` the contracts stay compiled for shanghai, so the pins, the real BLS checks
and the kit run in one pass on the canonical bytes. With `--evm-version prague` the compiler emits other bytes
(`DrandBeacon` is 5,819 instead of 5,841 bytes) and the byte pins skip themselves; the suites install the recorded
canonical beacon runtime (`drand-beacon-code.json`) so that the controller's code hash pin still holds.

| Suite | What it covers | Tests |
|---|---|---|
| `test/tools/drand/DrandCanonical.t.sol` | pinned hashes and sizes, the CREATE2 addresses, the VM and the linked reference collection, deployment through a copy of the deterministic deployer, no dangerous opcodes in the controller | 8 |
| `test/tools/drand/DrandBeacon.t.sol` | constants and time functions (fuzzed), 49 real rounds verified, `check` stores nothing, the cache path, `GasTooLow`, malformed and wrong signatures (lengths, flag bytes, x ≥ p, off-curve x, x + p, the negated point, other rounds, round 0, bit flips), nothing verifies without the precompiles | 16 |
| `test/tools/drand/TapDrandReveal.t.sol` | the factory and constructor, unreachable owner powers (the collection rejects everybody else, `revealFromBlockhash` reverts for every block, the dangerous selectors and opcodes are absent), commit and self-test failures, both modes (fixed window and `MIN_FIXED_LEAD`, deferred `scheduleDelay` bounds and public scheduling), the mint gateway and its closing, reveal, freeze, emergency path, lag cases, gas | 51 |
| `test/tools/drand/TapDrandRevealBLS.t.sol` | the kit end to end with real signatures (fixed and deferred), wrong round and wrong signature at the reveal and at the self-test, lag and posted rounds, the emergency path against the real verifier | 10 |

Counts of the 2026-10-25 runs (Foundry 1.8.3, native solc 0.8.28): the whole repository `forge test` 282 passed, 0
failed, 20 skipped (the 217 existing tests plus 65 of the kit; 30 suites). The kit alone with `--hardfork prague`: 84
passed, 0 failed, 1 skipped (the no-precompiles test). With `--evm-version prague`: 77 passed, 0 failed, 8 skipped (the
7 byte pins and the no-precompiles test).

The fixture `contracts/test/fixtures/drand-quicknet-rounds.json` holds 49 historical rounds. `fetch_drand_rounds.py`
takes each from `api.drand.sh` (the drand team) and `drand.cloudflare.com` (Cloudflare), and refuses to write anything
if the relays disagree on a signature, if a relay's `/info` does not hash to quicknet's chain hash or carries another
public key than the one in `DrandBeacon.sol`, or if randomness is not SHA-256 of the signature. It does not check the BLS
signatures; the tests do, on chain.

## 11. Differences and known issues

- **Emergency gas.** `revealUnverified` needs about 2.1M gas available (`SELFTEST_GAS + SELFTEST_GAS / 63 + 50,000`).
  Use 2.2M.
- **`newestRoundAtSchedule`.** In fixed mode it is `max(latestVerifiedRound, selfTestRound)`, because the self-test
  round's time enters the clock at the commit. In deferred mode it is `latestVerifiedRound`.
- **`scheduleDelay` in fixed mode.** The constructor checks its range in both modes, so a fixed-mode deployment passes
  the minimum, 3,600. Fixed mode never reads it.
- **Ordering and minting rights.** `closeMint` and `scheduleReveal` before the commit revert `NotCommitted`. The admin
  cannot mint unless it allows itself as a minter.
- **Storage.** The controller uses three packed slots plus `selfTestSig` and the minter mapping.
- **Review.** The contributor reviewed the contracts; this is not an audit. Three problems were found. A gateway left
  open after R under a lag seen at the commit was fixed. A fixed-mode commit of an already-public round under a
  chain-clock lag, and a deferred scheduler choosing among public rounds, have no on-chain fix: they were narrowed (the
  13 h minimum lead; `scheduleDelay` of 1 h to 7 days) and the remaining margins are the chain-clock residuals of
  section 2.
