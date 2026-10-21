---
tap: TBD
title: Soulbound Netlist Credentials
description: Non-transferable TAP-721 tokens that record a skill, a result or a contribution together with a netlist, and say whether the credential was proven by an on-chain check, attested by a named issuer or claimed by its holder.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/73
status: Draft
type: Standards
created: 2026-10-20
updated: 2026-10-21
requires: TAP-02, TAP-draft-netlist-bound-nft, TAP-draft-design-credits, ERC-165, ERC-721, ERC-1271, ERC-5192, EIP-712
license: CC0-1.0
---

# TAP-TBD: Soulbound Netlist Credentials

## Summary

This TAP defines badges that cannot be sold or moved, each carrying a real circuit, and that always say plainly whether a contract checked the circuit, an organisation vouched for the holder, or the holder only claims it.

## Abstract

A soulbound netlist credential is an ERC-721 token, locked under ERC-5192, whose metadata follows TAP-721 (`TAP-draft-netlist-bound-nft`) with the netlist bound at mint, and whose contract records a credential: its kind, its subject, the account responsible for its meaning, a scope, the netlist hash of its artifact, an optional evidence hash, its issue and expiry times and the token it replaces. There are three kinds with different trust models. A **proven** credential is minted by the contract itself when a submitted LATCH-free netlist with at most 16 inputs passes a specification committed on chain: the contract evaluates every input vector and compares a truth-table hash, within work bounds it publishes so that every check fits one transaction. Submissions are committed before they are revealed, commitments are recorded per committer, and a specification can reject renamed copies of designs accepted in earlier rounds by a design key equivalent to the structural hash. An **attested** credential is minted from an EIP-712 attestation signed by a named issuer (an externally owned account or an ERC-1271 contract), with optional expiry and revocation. A **claimed** credential is minted by its holder about itself. Any kind can name an agent account as its subject. Every mint is sent or authorised by the recipient; holders can always renounce; lost keys are handled by re-issue to a new account with a link to the old token, never by transfer, and a proven re-issue waits for a delay during which the old key can veto it. The TAP defines the interfaces, the hashes, the `tap.credential` metadata member, display rules, and a neutral read-only query. It defines no right to income, profit, tokens or any other payment.

## Motivation

The TapeOut community wants durable, public records that a person or an agent did something with circuits:

1. contributions to the foundation and to TapeOut projects;
2. design skill: "built a 4-bit adder in at most N gates";
3. results of contests;
4. design credits, today signed claims under `TAP-draft-design-credits`, landed on chain as tokens;
5. the identity and capabilities of agents that design or check circuits.

These records should not be tradable: a skill badge that can be bought says nothing about its holder. ERC-5192 gives a minimal, widely recognised lock flag for ERC-721 tokens, but it says nothing about who issued a token or why it should be believed. In practice three very different things end up looking the same in a wallet: a badge a contract issued because a netlist passed a check anyone can repeat, a badge an organisation issued because it says so, and a badge someone minted about themselves. Collapsing them misleads holders, employers, contest organisers and anyone who later relies on credentials.

TapeOut has an advantage that general soulbound-token schemes lack: the thing a credential is about is often a netlist, and netlists can be evaluated on chain. Under TAP-02 a LATCH-free netlist is a pure function, so "this netlist computes the specified function within the gate budget" can be checked by a contract, and re-checked by any wallet, without trusting anyone. This TAP makes that check precise, adds the commit-reveal and duplicate rules a contest needs, and puts attested and claimed credentials in the same token format with labels that keep them apart.

Every credential contract implements ERC-5192, the minimal soulbound interface for ERC-721 tokens, and this TAP adds what ERC-5192 leaves open for netlist credentials: who issued a credential, on what basis, and how it is displayed. The authors therefore request the number 5192 (proposal name TAP-5192, mirroring ERC-5192); because TAP-01 §6.1 otherwise assigns the lowest free number above 10, this needs the editors' agreement. Until a number is assigned, the draft keeps the file name `TAP-draft-soulbound-credentials.md` and `tap: TBD`; the editors assign the final number, and if it differs, the draft takes that number.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

### Conformance summary

This table is a guide to the sections below; where it and a section differ, the section prevails.

| Part | Status | Sections | Interface (ERC-165 id) |
|---|---|---|---|
| Soulbinding, credential record, statuses, consent, renouncing, rebinding | Core: every credential contract | §3 | ERC-721 (`0x80ac58cd`), ERC-5192 (`0xb45a3c0e`), ERC-165 (`0x01ffc9a7`) |
| Core interface | Core | §8.1 | `ITapCredential` (`0x5558759c`) |
| Proven issuance | Required of a contract that issues proven credentials | §4, §8.2 | `ITapCredentialProven` (`0x07aaf2dc`) |
| Attested issuance | Required of a contract that issues attested credentials | §5, §8.3 | `ITapCredentialAttested` (`0x7587c9da`) |
| Claimed issuance | Required of a contract that issues claimed credentials | §6, §8.4 | `ITapCredentialClaimed` (`0x11e35684`) |
| Agent subjects | Optional for any kind | §7 | — |
| Metadata (`tap.credential`) | Core | §9 | — |
| Display rules | Every tool that displays credentials | §10 | — |

### 1. Terms and notation

| Term | Meaning |
|---|---|
| Credential contract | An ERC-721 contract that follows this TAP |
| Credential | A token of a credential contract, with its credential record (§3.4) |
| Holder | The current `ownerOf` of a credential |
| Kind | `proven` (1), `attested` (2) or `claimed` (3) |
| Subject | `account` (0) or `agent` (1): what the holder address stands for (§7) |
| Artifact | The netlist bound to a credential, identified by its netlist hash (`TAP-draft-netlist-bound-nft` §2.3) |
| Combinational file | A valid `tapnet/1` file (`TAP-draft-netlist-bound-nft` §2.2) without LATCH records |
| Specification | The committed rules a proven credential is checked against (§4.4) |
| Round | One specification: one commit window followed by one reveal window |
| Series | Rounds of one registrant that share a duplicate-design namespace (§4.4) |
| Issuer | The account responsible for what a credential means (§3.4); not a verified identity |
| Tool | Software that displays credentials or reads them for others |

Byte strings are written in hexadecimal with a `0x` prefix. `‖` is concatenation. `u8(x)`, `u32be(x)` and `u64be(x)` are big-endian unsigned integers of 1, 4 and 8 bytes; an address is its 20 bytes. SHA-256 is FIPS 180-4; `keccak256` is the hash of EIP-712. `ASCII(s)` is the bytes of string `s`. Hashes and addresses in JSON are lowercase hexadecimal with `0x`. Times are Unix seconds compared with `block.timestamp`.

### 2. Scope and non-claims

A credential records that something happened or was checked. It is not a financial instrument.

1. A credential does not confer, and credential contracts, issuers, producers of metadata and tools MUST NOT present it as conferring: any right to income, revenue, profit share, yield, dividends, tokens, airdrops, allocations, rewards or any other payment or asset; any claim on an issuer, a foundation or a treasury; ownership of a netlist, a circuit token, a container or a TAP-721 token other than the credential itself; exclusivity over a design; or verification of anyone's identity.
2. A credential contract MUST NOT transfer, mint, lock or release any asset other than its own credential tokens as a consequence of issuing, holding, renouncing, rebinding, revoking or querying a credential, and MUST NOT take payment for issuance beyond the gas of the transaction.
3. The whole metadata document of a credential (§9), including the ERC-721 members `name`, `description` and `attributes`, MUST NOT contain a member, an attribute or text that states or suggests a monetary value, a price, a yield, a share, a weight, points, a tier, a multiplier, an allocation, an airdrop, a reward, an expected payment or eligibility for a payment (§9 item 2). The member `tap.pod` of `TAP-draft-pod-attributes` is exempt; that TAP's own non-entitlement rules apply to it (§9 item 2).
4. The query of §8.1 is neutral: it returns facts about credentials of one kind and assigns them no weight. A program that uses credentials in its own decisions is outside this TAP and is responsible for its own rules.

Netlist-bound tokens under TAP-721 carry no right over the source circuit or anything it earns (`TAP-draft-netlist-bound-nft` §3.2); this TAP keeps that position and adds nothing to it.

### 3. Credential tokens

#### 3.1 Soulbinding

A credential contract MUST implement ERC-721, ERC-165 and ERC-5192, and MUST report the ERC-165 identifiers of ERC-721 (`0x80ac58cd`), ERC-5192 (`0xb45a3c0e`), ERC-165 (`0x01ffc9a7`) and `ITapCredential` (§8.1).

1. `locked(tokenId)` MUST return `true` for every existing credential and MUST revert for a token that does not exist;
2. `transferFrom` and both `safeTransferFrom` functions MUST revert for every credential, whoever calls them;
3. `approve` and `setApprovalForAll` MUST revert, so that no approval suggests that a transfer is possible;
4. the contract MUST emit `Locked(tokenId)` in the transaction that mints a credential and MUST NOT emit `Unlocked`;
5. renouncing (§3.7), which burns the credential, is the only way a credential leaves its holder. Rebinding (§3.8) mints a new token and leaves the old one with its holder.

#### 3.2 Relation to TAP-721

Every credential is a TAP-721 token whose netlist is bound at mint: a collection without a manifest (`TAP-draft-netlist-bound-nft` §7.2) that records each token's netlist hash at mint, as a mint-bound collection of `TAP-draft-netlist-bound-nft` §8.2 does. Its metadata MUST follow `TAP-draft-netlist-bound-nft` §7 with `tap.state` = `revealed` and without `tap.manifest`. `tap.image`, which TAP-721 §7.1 requires in state `revealed`, MUST be present; it MAY describe a badge image shared by many credentials. `tap.netlist.sha256` MUST equal the artifact of the credential record. Credentials do not form TAP-721 editions (`TAP-draft-netlist-bound-nft` §6.4), even when many of them share an artifact such as a badge circuit, because they are minted with their netlist and have no manifest and no reveal; their metadata MUST NOT contain `tap.edition`.

A credential contract therefore conforms to TAP-721 at L0 for its metadata. It MUST NOT report the ERC-165 identifier of `ITapNetlistNFT` (`0x282b67f6`) unless it implements that interface in full. Without a manifest, L1 is open only to a contract that implements the mint-bound profile of `TAP-draft-netlist-bound-nft` §8.2 (part of a proposed amendment to that draft, not yet merged), and L1 also requires ERC-4906, which a credential contract does not report (below); a credential contract therefore stays at L0. The artifact is nevertheless recorded on chain: `netlistHashOf` (§8.1) returns it, and tools show both facts together (§10.1 item 5).

TAP-721 §8.1 rests the L0 guarantee that content will not change on the collection giving up the power to change `tokenURI`. A credential contract MUST fix the `tokenURI` of every credential at its mint and MUST provide no way to change it afterwards; the producer of the metadata MUST NOT change the document that URI serves, and SHOULD use content-addressed URIs so that readers can check this. Status is kept by the contract (§3.5), so no change to a credential ever requires a change to its metadata: a credential contract MUST NOT emit the ERC-4906 events `MetadataUpdate` and `BatchMetadataUpdate` and MUST NOT report the ERC-165 identifier of ERC-4906 (`0x49064906`). Whether `tokenURI` is fixed cannot be read from the chain; a tool establishes it by the code check of §10.1 item 4 and displays it under §10.1 item 5.

The artifact file MUST be a valid `tapnet/1` file. A credential contract MUST make every artifact file readable through `netlistFile` (§8.1) no later than the mint of the first credential that names it.

#### 3.3 Kinds and subjects

| Kind | Who decides that the credential is deserved | What a reader can check |
|---|---|---|
| `proven` (1) | The credential contract, by the checks of §4 | The artifact against the specification, by re-running the check (§10.2) |
| `attested` (2) | The issuer, by signing an attestation (§5) | The issuer's signature or contract approval; nothing about the truth of the attestation |
| `claimed` (3) | The holder, by minting it about itself (§6) | Only that the holder made the claim |

The subject is `account` (0) when the holder address stands for a person or organisation, and `agent` (1) when it is the operating account of a software agent (§7). The subject does not change the kind.

#### 3.4 Credential record

For every credential the contract keeps the record below and returns it from `credentialOf` (§8.1). Once minted, a record never changes; status changes are kept separately (§3.5).

| Field | Type | Proven | Attested | Claimed |
|---|---|---|---|---|
| `kind` | `uint8` | 1 | 2 | 3 |
| `subject` | `uint8` | 0 or 1, fixed by the commitment (§4.5) | from the attestation | chosen by the holder |
| `issuer` | `address` | the specification's registrant: who defined what passes | the attestation's issuer | the holder that minted it |
| `scope` | `bytes32` | the specification id (§4.4) | the attestation's scope (§5.2) | the claim scope of a Design Credits statement id, or zero (§6) |
| `artifact` | `bytes32` | the netlist hash of the accepted file | the attestation's artifact | the netlist hash of the claimed file |
| `evidence` | `bytes32` | zero | SHA-256 of an evidence document, or zero | SHA-256 of an evidence document, or zero |
| `issuedAt` | `uint64` | the block timestamp of the mint | the attestation's `issuedAt`, at most the block timestamp of the mint (§5.4) | the block timestamp of the mint |
| `expiresAt` | `uint64` | zero (no expiry) | from the attestation; zero for none | zero |
| `replaces` | `uint256` | the old token id after a rebind (§4.7), otherwise zero | the old token id after a re-issue (§5.6), otherwise zero | zero |

Token ids start at 1, so zero in `replaces` means none.

#### 3.5 Statuses

`statusOf(tokenId)` returns:

| Value | Status | Meaning |
|---|---|---|
| 0 | none | The token does not exist (never minted, or renounced) |
| 1 | active | None of the below |
| 2 | expired | `expiresAt` ≠ 0 and `block.timestamp` ≥ `expiresAt` |
| 3 | revoked | The issuer revoked the attestation it was minted from (§5.5) |
| 4 | superseded | A rebind or re-issue minted a replacement (§3.8) |

Revoked and superseded are permanent and exclude each other (§5.5, §5.6); expired is returned only while neither applies. Values above 4 are reserved. Every change to status 3 or 4 MUST emit `CredentialStatusChanged(tokenId, status)` (§8.1). Status is state of the chain: it MUST NOT be written into metadata (§9), and tools MUST read it from the contract (§10).

#### 3.6 Consent

No credential may be minted to an account that did not ask for it. A credential contract MUST mint a credential to `recipient` only in one of these cases:

1. proven: `recipient` sent a commit transaction (§4.5) that recorded, for `recipient`, the commitment naming it; the reveal MAY be sent by anyone;
2. attested: `recipient` is `msg.sender` of the redemption (§5.4);
3. claimed: the holder is `msg.sender` of the claim (§6);
4. rebinding: the new holder is `msg.sender` of the rebind request and of its completion (§4.7), or of the re-issue (§5.6).

A contract account, including an agent's account (§7), consents by making the call itself.

#### 3.7 Renouncing

`renounce(tokenId)` MUST burn the credential when called by its holder, and MUST revert for any other caller. Burning emits the ERC-721 `Transfer` to the zero address and `CredentialStatusChanged(tokenId, 0)`. Renouncing a proven credential also deletes a pending rebind request for it (§4.7). After renouncing, `statusOf` returns 0, `ownerOf`, `credentialOf`, `netlistHashOf` and `locked` revert, and the token is never minted again. No other account can burn a credential: an issuer that withdraws an attestation revokes it (§5.5).

#### 3.8 Rebinding instead of transfer

A holder who loses its key cannot move its credentials. A replacement is a new token:

- for an attested credential, the issuer signs a new attestation with `replaces` = the old token id (§5.6);
- for a proven credential, the specification's recovery authority, if it named one, signs a `Rebind`; the replacement is minted only after a delay during which the old holder can veto it (§4.7).

A proven replacement copies the old record except `issuedAt` (the new mint) and `replaces` (the old token id), and is never minted to an account that holds or held a credential of the same specification. An attested replacement takes its record from the new attestation, whose issuer must equal the old one (§5.6); the issuer may so renew an expiry or correct a scope. In both cases the old token keeps its holder and gets status superseded; the contract emits `CredentialRebound(oldTokenId, newTokenId)`. A superseded credential cannot be rebound again, and a revoked attested credential cannot be re-issued. Claimed credentials are not rebound: the holder of a new key claims again.

### 4. Proven credentials

#### 4.1 What can be proven

Version 1 proves one statement: the submitted file is a combinational file with the specification's `nIn` (at most 16) and `nOut`, has at most `maxGates` NAND records, and computes the specified function on every input vector. Input vector `x`, for `0 ≤ x < 2^nIn`, sets input `i` to bit `i` of `x`, which is the packing of TAP-02 §5 read as a little-endian integer. Files with more than 16 inputs or with LATCH records, sequential behaviour and `tapnet/2` files are out of scope (§4.8).

#### 4.2 Truth tables

For a combinational file with `nIn ≤ 16`, column `j` (`0 ≤ j < nOut`) is the string of `2^nIn` bits whose bit `x` is output `j` for input vector `x`, written most significant bit first: bit `x` is bit `7 − (x mod 8)` of byte `⌊x / 8⌋`. A column has `max(1, 2^nIn / 8)` bytes; for `nIn < 3` its unused low bits are zero.

```
truthTable     = u32be(nIn) ‖ u32be(nOut) ‖ column_0 ‖ … ‖ column_{nOut−1}
truthTableHash = SHA-256(ASCII("tap-credential-truth-table/1") ‖ 0x00 ‖ truthTable)
```

Examples (informative, from `vectors.json`): the two-input XOR has `truthTable` = `0x000000020000000160` and `truthTableHash` = `0xd33c6800252db2f67a985dbb4a7d7a68c0babd8b03d2f95bfea65d836990dd2e`. A registrant can compute the hash from the intended function without publishing any netlist.

#### 4.3 Design keys

For a combinational file, every signal `s` has a label `λ(s)`, with `L(x) = SHA-256(ASCII("TAPSH1") ‖ x)` and labels compared as 32-byte strings:

- constant 0 (signal 0): `L(0x00 ‖ 0x00)`; constant 1 (signal 1): `L(0x00 ‖ 0x01)`;
- input `i` (signal `2 + i`): `L(0x01 ‖ u32be(i))`;
- the element `NAND(a, b)`: `L(0x02 ‖ min(λ(a), λ(b)) ‖ max(λ(a), λ(b)))`.

Because a NAND reads only smaller signal indices, one pass in file order labels every element. These are the labels of `TAP-draft-netlist-structural-hash` §4.1–§4.2 restricted to files without LATCH records. With `S = 2 + nIn + nand`, output `j` is signal `S − nOut + j` (TAP-02 §3).

```
designKey = SHA-256(ASCII("tap-credential-design-key/1") ‖ 0x00 ‖ u32be(nIn) ‖ u32be(nOut)
                    ‖ λ(output 0) ‖ … ‖ λ(output nOut−1))
```

For combinational files, two files have the same design key if and only if they have the same structural hash (`TAP-draft-netlist-structural-hash` §7), assuming SHA-256 has no collisions on the inputs involved (Rationale). The design key is defined separately because a contract can compute it in one pass with one SHA-256 call per gate, without the canonical ordering the structural hash needs. Tools display the structural hash (§9); contracts compare design keys.

#### 4.4 Specifications

A specification is the tuple

| Field | Type | Rule |
|---|---|---|
| `registrant` | `address` | The account that registers it; MUST equal `msg.sender` of `registerSpec` |
| `nIn`, `nOut` | `uint32` | `0 ≤ nIn ≤ 16`, `1 ≤ nOut ≤ 65536` |
| `target` | `bytes32` | The `truthTableHash` (§4.2) of the function. Not zero |
| `maxGates` | `uint32` | Upper bound on NAND records, at least `nOut` |
| `unique` | `bool` | Whether designs revealed in any earlier round of the series are rejected (§4.6 item 8). Requires a non-zero `series` |
| `series` | `bytes32` | Zero, or a value the registrant chooses to group rounds |
| `commitStart`, `commitEnd`, `revealEnd` | `uint64` | `commitStart < commitEnd < revealEnd` |
| `recoveryAuthority` | `address` | Zero, or the account that may sign rebinds (§4.7) |
| `infoHash` | `bytes32` | SHA-256 of a document describing the task in words; MAY be zero |

```
specId    = SHA-256(ASCII("tap-credential-spec/1") ‖ 0x00 ‖ registrant ‖ u32be(nIn) ‖ u32be(nOut) ‖ target
                    ‖ u32be(maxGates) ‖ u8(unique) ‖ series ‖ u64be(commitStart) ‖ u64be(commitEnd)
                    ‖ u64be(revealEnd) ‖ recoveryAuthority ‖ infoHash)
seriesKey = SHA-256(ASCII("tap-credential-series/1") ‖ 0x00 ‖ registrant ‖ series)
```

Registration MUST revert unless every rule above holds and, in addition:

1. no specification with the same `specId` exists;
2. the contract can perform every check of §4.6, including storing the file, for every file the specification admits within one transaction of at most 16,777,216 gas (the transaction gas limit of EIP-7825), leaving room for calldata. A contract MUST refuse to register a specification it could not check, MUST publish its bounds as constants and through `checkBounds` and `specOf` (§8.2), and MUST NOT change them. The reference implementation uses two bounds, chosen from measurements (Rationale):
   - gate work: `(max(1, 2^nIn / 256) + 20) · maxGates ≤ 65,536`, where one unit is one NAND evaluated on one 256-lane word and the 20 charges the per-gate costs that do not depend on `nIn` (file check, design key, storage of the file);
   - truth-table buffer: `nOut · max(1, 2^nIn / 8) ≤ 131,072` bytes;
3. if `series` is not zero, `commitStart` is at or after the `revealEnd` of every earlier round of the same `seriesKey`. Rounds of a series therefore never overlap.

Registering a specification does not make the registrant's description true: the specification's meaning in words is whatever `infoHash` fixes, and tools show the registrant (§10).

#### 4.5 Commitments

```
commitment = SHA-256(ASCII("tap-credential-commit/1") ‖ 0x00 ‖ specId ‖ recipient ‖ u8(subject)
                     ‖ netlistHash ‖ salt)
```

where `netlistHash` is the SHA-256 of the file to be revealed and `salt` is 32 bytes chosen by the recipient, which SHOULD be random. `commit(specId, commitment)` MUST revert outside `commitStart ≤ block.timestamp < commitEnd`, for an unknown specification and for a commitment already recorded by `msg.sender` for that specification; otherwise it records the commitment for `msg.sender` and emits `Committed(specId, msg.sender, commitment)`. Commitments are recorded per committer: the same commitment recorded by another account neither blocks nor helps `msg.sender`. A reveal succeeds only with a commitment recorded by the recipient named inside it (§4.6 item 2), so a commitment cannot be redirected to another recipient, and copying someone else's pending commit transaction gains nothing.

#### 4.6 Reveal

`reveal(specId, recipient, subject, file, salt)` MAY be sent by anyone. It MUST revert unless all of the following hold, in any order:

1. `commitEnd ≤ block.timestamp < revealEnd`;
2. the commitment computed from the arguments was recorded by `recipient` for this specification (§4.5) and not yet consumed;
3. `recipient` holds or held no credential of this specification, whether obtained by a reveal or received by a rebind (§4.7): each account obtains at most one proven credential per specification;
4. `file` is a combinational file of at most 49,152 bytes;
5. its `nIn` and `nOut` equal the specification's, and its number of NAND records is at most `maxGates`;
6. its `truthTableHash` (§4.2) equals `target`;
7. its design key (§4.3) is computed;
8. if `unique` is true: no earlier round of the same series, whether `unique` or not, has recorded the same design key (below). Submissions of the same round never exclude each other, because all of them were committed before any of them was revealed.

On success the contract consumes the commitment, stores the file, mints the credential to `recipient`, and emits `Accepted(tokenId, specId, recipient, netlistHash, designKey)`. If `series` is not zero, it also records the design key for the series, whether or not `unique` is true, so that every later `unique` round of the series rejects it.

`unique` is a narrow guarantee. It compares design keys, so a function-preserving rewrite (for example a double negation, which a tight `maxGates` may or may not exclude) escapes it, and it covers only the rounds of one registrant's series: another registrant's specifications, or a new series, do not see earlier answers. A credential of a `unique` specification shows that its design key was not revealed in an earlier round of that series, not that the design is original (§10.2 item 4).

#### 4.7 Recovery of proven credentials

If a specification names a `recoveryAuthority`, that account MAY sign a `Rebind` (§5.1). Recovery takes three calls:

1. `requestRebind(request, signature)` MUST revert unless `msg.sender` is `request.newHolder`; the old token exists, is proven and is not superseded; its specification's `recoveryAuthority` is not zero and equals `request.authority`; `deadline` is zero or not passed; `newHolder` holds or held no credential of the specification; the signature is valid for the authority under §5.3; and the same `Rebind` digest was not used before. It then marks the digest used, records the request with `readyAt = block.timestamp + REBIND_DELAY`, replacing any request recorded for the old token, and emits `RebindRequested(oldTokenId, newHolder, readyAt)`. The reference implementation sets `REBIND_DELAY` to 604,800 seconds (seven days); a contract MUST publish its delay and MUST NOT set it below one day.
2. `vetoRebind(oldTokenId)` MUST revert unless `msg.sender` holds the old token and a request for it is pending. It deletes the request and emits `RebindVetoed(oldTokenId)`. A holder that still has its key can so stop a corrupt or mistaken authority; renouncing the old token has the same effect.
3. `completeRebind(oldTokenId)` MUST revert unless a request for the old token is pending, `msg.sender` is its `newHolder`, `readyAt ≤ block.timestamp < readyAt + REBIND_DELAY`, the old token still exists and is not superseded, and `newHolder` still holds or held no credential of the specification. It then deletes the request, records that `newHolder` holds a credential of the specification, and rebinds under §3.8.

A request is pending from its `RebindRequested` until it is completed, vetoed or replaced, until the old token is renounced, or until `readyAt + REBIND_DELAY`: a request that is not completed within `REBIND_DELAY` after it became ready lapses and can no longer be completed or vetoed. A new `Rebind` signed by the authority and requested under item 1 replaces a pending or lapsed request and restarts the delay, so that a request nobody completes cannot block recovery, and the request that can be completed has always left the old holder a full delay to veto it. Renouncing the old token deletes its request (§3.7). A vetoed or replaced request does not come back: its digest stays used, and the authority signs a new `Rebind` with a new `nonce` if it still wants to rebind. If the specification names no authority, a proven credential cannot be rebound; for a specification without `unique`, the holder of a new key can obtain the credential again in a later round.

#### 4.8 Larger, sequential and optimistic checking (informative)

Version 1 proves only what a contract checks in full within one transaction (§4.4 item 2). An earlier draft accepted larger files optimistically against a public reference netlist; it was removed because the largest files did not fit one transaction, the public reference gave the answer away, and "proven" became "not yet refuted". A later version could prove larger, sequential (LATCH) or `tapnet/2` netlists with the dispute game of `TAP-draft-large-netlists` §7, under its own interface, with its own status for a disproved claim and its own label, distinct from "Proven".

### 5. Attested credentials

#### 5.1 EIP-712 domain and types

```
EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)
name    = "TAP Soulbound Credentials"
version = "1"
chainId = the chain id of the credential contract
verifyingContract = the credential contract

Attestation(address issuer,address recipient,uint8 subject,bytes32 scope,bytes32 artifact,bytes32 evidence,uint64 issuedAt,uint64 expiresAt,uint64 deadline,uint256 replaces,bytes32 nonce)

Rebind(address authority,uint256 oldTokenId,address newHolder,uint64 deadline,bytes32 nonce)
```

`digest = keccak256(0x19 ‖ 0x01 ‖ domainSeparator ‖ hashStruct(message))` as in EIP-712. The digest of an attestation is its **attestation id**. The type hashes are `Attestation` `0x228dbd1f2d086ffc2f8992a5c372964d588ea1745ce363fb4a770c7848126d5e` and `Rebind` `0x608e975c3778a409ea42f524f1487367e7114b1e711368291409ea557222972d`. Unlike Design Credits statements, attestations are bound to one contract on one chain, because a contract mints from them.

#### 5.2 Field rules

| Field | Rule |
|---|---|
| `issuer` | Not zero. Signs the attestation, or as a contract approves it under ERC-1271 |
| `recipient` | Not zero. The only account that may redeem it |
| `subject` | 0 or 1 (§3.3) |
| `scope` | Not zero. What the attestation is about. An issuer that names the scope in words SHOULD use `SHA-256(ASCII("tap-credential-scope/1") ‖ 0x00 ‖ UTF-8(label))`, so that tools can show the label (§9) |
| `artifact` | Not zero. The netlist hash of the credential's artifact: the passed design, the contest entry, or a badge circuit |
| `evidence` | Zero, or the SHA-256 of an evidence document |
| `issuedAt` | When the issuer made the attestation, as declared by the issuer; not later than the redemption. It becomes the record's `issuedAt` |
| `expiresAt` | Zero, or a time after `issuedAt` at which the credential expires; an attestation whose `expiresAt` has passed cannot be redeemed |
| `deadline` | Zero, or the last time at which the attestation can be redeemed |
| `replaces` | Zero, or the token id it replaces (§5.6) |
| `nonce` | Any 32 bytes; distinguishes otherwise identical attestations |

#### 5.3 Signatures

A signature for signer `A` over digest `h` is valid if either of the following holds, checked in this order:

1. the signature is exactly 65 bytes `r ‖ s ‖ v` with `v` ∈ {0, 1, 27, 28}, where 0 and 1 stand for 27 and 28 (as in `TAP-draft-design-credits` §4.6); `r` and `s` are not zero; `s ≤ n/2` where `n` is the order of secp256k1; and `ecrecover(h, v, r, s)` returns `A`;
2. `A` has code at the time of the call, and `isValidSignature(h, signature)` (ERC-1271, selector `0x1626ba7e`) on `A` returns a value whose first four bytes are `0x1626ba7e`.

A contract MUST try item 1 before item 2, whether or not `A` has code: an externally owned account with an EIP-7702 delegation has code but keeps its key, and its key signature MUST NOT depend on what the delegated code answers.

#### 5.4 Redemption

`redeem(attestation, signature)` MUST revert unless: the fields follow §5.2; `issuedAt ≤ block.timestamp`; `expiresAt` is zero or greater than `block.timestamp`; `msg.sender` is `recipient`; the attestation id has been neither redeemed nor revoked; `deadline` is zero or not passed; the signature is valid for `issuer` (§5.3); the artifact file is readable through `netlistFile` (any account can store a valid file with `storeNetlist`, §8.1); and, if `replaces` is not zero, §5.6 holds. It then mints the credential with the record of §3.4, whose `issuedAt` is the attestation's, and remembers the token minted from the attestation id. Attested credentials accumulate: there is no limit of one per issuer and scope, and an account can hold several attested credentials with the same issuer and scope, each redeemed from its own attestation.

#### 5.5 Revocation

`revokeAttestation(attestation)` MUST revert unless `msg.sender` is the attestation's issuer. It marks the attestation id revoked, emits `AttestationRevoked(attestationId, issuer)`, and gives the credential minted from it, if it exists and is active or expired, status revoked. An attestation revoked before redemption can never be redeemed. Revocation does not burn the credential: the holder keeps a visible, revoked token, which it may renounce. For a contract issuer the call comes from the contract itself.

#### 5.6 Re-issue

An attestation with `replaces` = `t` can be redeemed only if token `t` exists, is attested, has the same `issuer`, and is neither superseded nor revoked. An expired credential can be re-issued; this is how an issuer renews an expiry. Redemption then rebinds under §3.8. The recipient of the replacement MAY differ from the old holder: re-issue is how an issuer moves a credential to a holder's new key. Re-issue has no delay and no veto: the issuer already decides what its credentials mean (Security Considerations).

#### 5.7 Issuer identity

The issuer of an attested credential is an address. Nothing in this TAP establishes who controls it. A name for the issuer appears only as the self-declared `issuerName` of the metadata (§9), displayed under §10.3.

### 6. Claimed credentials

`claim(file, statementId, evidence, subject)` mints to `msg.sender` a credential of kind claimed whose `issuer` is `msg.sender`, whose artifact is the netlist hash of `file`, and whose `scope` is the claim scope of `statementId`:

```
claimScope(statementId) = 0x00…00                                                        if statementId = 0
                        = SHA-256(ASCII("tap-credential-claim/1") ‖ 0x00 ‖ statementId)   otherwise
```

It MUST revert unless `file` is a valid `tapnet/1` file of at most 49,152 bytes and `subject` is 0 or 1; it stores the file. Hashing the statement id keeps the scopes of claimed credentials apart from specification ids and attestation scopes, so that a holder cannot make its claim share a scope value with a proven or attested credential.

A claim MAY land a Design Credits statement (`TAP-draft-design-credits` §4) on chain: `statementId` is then that statement's id, and the metadata carries the statement (§9). The credential contract does not verify the statement. A tool that displays it MUST verify it under `TAP-draft-design-credits` §4.6 and MAY show it as the holder's statement about the artifact only if all of the following hold:

1. its signer corresponds to the holder: `signer` equals the holder and `signerChainId` is 0 (a key signature) or the chain id of the credential contract (a contract account at the holder's address on the same chain);
2. its `subject` applies to the artifact in the sense of `TAP-draft-design-credits` §3.3: a non-zero `netlistHash` equals the artifact and a non-zero `structuralHash` equals the artifact file's structural hash;
3. it is not revoked under `TAP-draft-design-credits` §4.7, judged with every Revocation the tool knows.

Otherwise the tool MUST show the statement's signer next to the holder and mark the statement "mismatch" (items 1 or 2) or "revoked" (item 3), and MUST NOT present it as supporting the credential. A tool MUST re-check revocations whenever it displays the statement, so that a statement revoked after the claim is shown as revoked; the credential keeps its status, because a claim stays a claim (its holder may renounce it). The contract MUST NOT be displayed as having verified the statement, and a claimed credential is a claim by its holder and nothing more, even when its artifact also appears in a proven credential.

### 7. Agent credentials

A credential with subject `agent` says that its holder address is the operating account of a software agent; its kind says, as for any credential, who decided that it is deserved. Agent capability credentials are proven (for example, an agent's account passes a specification) or attested (an operator or evaluator vouches for an agent).

1. The holder MUST be the agent's operating account (an externally owned account or a contract), and that account consents under §3.6 by sending the commit or the redemption itself.
2. The credential is bound to that account, not to any transferable identity token. A registry entry that can change hands, such as an ERC-8004 agent identity, MUST NOT be the holder.
3. The metadata MAY name an agent identity in `agent` (§9) in the form `eip155:<chainId>:<registry address>` and a decimal `agentId`. That link is a statement of the metadata producer. A tool that displays it SHOULD check, at a recent block and by the means the registry provides, that the registry associates `agentId` with the holder address, and MUST label the link "unconfirmed" when it does not or when the tool cannot check it. ERC-8004 is a Draft whose interface may change; this TAP depends on none of its functions (Rationale).

### 8. Interfaces

#### 8.1 `ITapCredential`

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

interface ITapCredential {
    struct Credential {
        uint8 kind;          // 1 proven, 2 attested, 3 claimed
        uint8 subject;       // 0 account, 1 agent
        address issuer;
        bytes32 scope;
        bytes32 artifact;    // netlist hash
        bytes32 evidence;
        uint64 issuedAt;
        uint64 expiresAt;
        uint256 replaces;
    }

    function credentialOf(uint256 tokenId) external view returns (Credential memory);
    function statusOf(uint256 tokenId) external view returns (uint8);   // §3.5
    function credentialsOf(address holder, uint8 kind, address issuer, bytes32 scope, bool activeOnly,
        uint256 cursor, uint256 limit) external view returns (uint256[] memory tokenIds, uint256 nextCursor);
    function netlistHashOf(uint256 tokenId) external view returns (bytes32);
    function netlistFile(bytes32 netlistHash) external view returns (bytes memory);
    function storeNetlist(bytes calldata file) external returns (bytes32 netlistHash);
    function renounce(uint256 tokenId) external;

    event CredentialIssued(uint256 indexed tokenId, address indexed holder, uint8 indexed kind,
        uint8 subject, address issuer, bytes32 scope, bytes32 artifact);
    event CredentialStatusChanged(uint256 indexed tokenId, uint8 status);
    event CredentialRebound(uint256 indexed oldTokenId, uint256 indexed newTokenId);
}
```

1. `credentialOf` and `netlistHashOf` revert for a token that does not exist; `netlistHashOf` returns the record's `artifact`. `statusOf` never reverts.
2. `credentialsOf` is the neutral query. It MUST revert unless `kind` is 1, 2 or 3 and `limit` is at least 1: a query always reads one kind, so that credentials of different kinds are never returned, counted or compared as one list. It returns, in mint order, credentials of that kind currently held by `holder` that match every other filter given: `issuer` (zero = any), `scope` (zero = any) and, if `activeOnly`, status active at the current block. It returns at most `limit` ids. `nextCursor` is zero when the list is complete; otherwise passing it as `cursor` continues the list. Cursor values are otherwise opaque. The function returns facts only and MUST NOT weight, score or rank credentials.
3. `storeNetlist` accepts any valid `tapnet/1` file of at most 49,152 bytes from any caller, stores it, and returns its netlist hash; `netlistFile` returns a stored file and reverts for an unknown hash. A stored file says nothing about any credential.
4. `CredentialIssued` is emitted at every mint, after ERC-721 `Transfer` and ERC-5192 `Locked`.

#### 8.2 `ITapCredentialProven`

```solidity
interface ITapCredentialProven {
    struct Spec {
        address registrant; uint32 nIn; uint32 nOut; bytes32 target; uint32 maxGates; bool unique;
        bytes32 series; uint64 commitStart; uint64 commitEnd; uint64 revealEnd; address recoveryAuthority;
        bytes32 infoHash;
    }
    struct Rebind { address authority; uint256 oldTokenId; address newHolder; uint64 deadline; bytes32 nonce; }

    function registerSpec(Spec calldata spec) external returns (bytes32 specId);
    function specOf(bytes32 specId) external view
        returns (Spec memory spec, uint256 maxGateWork, uint256 maxTableBytes);
    function checkBounds() external view returns (uint256 maxGateWork, uint256 maxTableBytes);
    function commit(bytes32 specId, bytes32 commitment) external;
    function reveal(bytes32 specId, address recipient, uint8 subject, bytes calldata file, bytes32 salt)
        external returns (uint256 tokenId);
    function requestRebind(Rebind calldata request, bytes calldata signature) external returns (uint64 readyAt);
    function vetoRebind(uint256 oldTokenId) external;
    function completeRebind(uint256 oldTokenId) external returns (uint256 tokenId);

    event SpecRegistered(bytes32 indexed specId, address indexed registrant);
    event Committed(bytes32 indexed specId, address indexed committer, bytes32 commitment);
    event Accepted(uint256 indexed tokenId, bytes32 indexed specId, address indexed recipient,
        bytes32 netlistHash, bytes32 designKey);
    event RebindRequested(uint256 indexed oldTokenId, address indexed newHolder, uint64 readyAt);
    event RebindVetoed(uint256 indexed oldTokenId);
}
```

`specOf` reverts for an unknown id; with the specification it returns the bounds under which the contract registered it. `checkBounds` returns the same bounds before any registration, so that a tool can tell in advance whether a specification will be accepted. The meaning of the two numbers is the contract's own and MUST be published with it (§4.4 item 2); the reference implementation returns 65,536 and 131,072 for the formulas given there.

#### 8.3 `ITapCredentialAttested`

```solidity
interface ITapCredentialAttested {
    struct Attestation {
        address issuer; address recipient; uint8 subject; bytes32 scope; bytes32 artifact; bytes32 evidence;
        uint64 issuedAt; uint64 expiresAt; uint64 deadline; uint256 replaces; bytes32 nonce;
    }

    function redeem(Attestation calldata attestation, bytes calldata signature) external returns (uint256 tokenId);
    function revokeAttestation(Attestation calldata attestation) external;
    function attestationStatus(bytes32 attestationId) external view returns (uint8 state, uint256 tokenId);

    event AttestationRevoked(bytes32 indexed attestationId, address indexed issuer);
}
```

`attestationStatus` returns `state` 0 (unknown), 1 (redeemed) or 2 (revoked), and the token minted from the attestation or zero.

#### 8.4 `ITapCredentialClaimed`

```solidity
interface ITapCredentialClaimed {
    function claim(bytes calldata file, bytes32 statementId, bytes32 evidence, uint8 subject)
        external returns (uint256 tokenId);
}
```

#### 8.5 Identifiers

A contract reports through ERC-165 exactly the interfaces it implements. The identifiers, function selectors and event topics are listed in `vectors.json` (section `interfaces`):

| Interface | ERC-165 id |
|---|---|
| `ITapCredential` | `0x5558759c` |
| `ITapCredentialProven` | `0x07aaf2dc` |
| `ITapCredentialAttested` | `0x7587c9da` |
| `ITapCredentialClaimed` | `0x11e35684` |
| ERC-5192 | `0xb45a3c0e` |

`netlistHashOf(uint256)`, `netlistFile(bytes32)` and `storeNetlist(bytes)` have the same selectors as the functions of the same names in TAP-721's `ITapNetlistNFT`, with different rules for `storeNetlist` (Security Considerations). Revert data is not part of these interfaces.

### 9. Metadata

The metadata of a credential follows `TAP-draft-netlist-bound-nft` §7 (§3.2) and its `tap` object MUST contain a member `credential`:

| Member | Required | Type | Content |
|---|---|---|---|
| `v` | yes | number | `1` |
| `kind` | yes | string | `"proven"`, `"attested"` or `"claimed"` |
| `subject` | yes | string | `"account"` or `"agent"` |
| `contract` | yes | object | `chainId` (number) and `address` (lowercase): the credential contract, which is the status source (§3.5). MUST match `tap.id` |
| `issuer` | yes | string | The record's `issuer` |
| `scope` | yes | string | The record's `scope` |
| `issuedAt`, `expiresAt` | yes | number | The record's values |
| `replaces` | when not zero | string | The record's `replaces`, decimal |
| `evidence` | when the record's `evidence` is not zero | object | `sha256` (equal to the record's), `uris` |
| `spec` | proven: required; other kinds: absent | object | `id` (= `scope`), `nIn`, `nOut`, `target`, `maxGates`, `unique`, `series`; optionally `info`: `sha256` (= `infoHash`), `uris` |
| `scopeLabel` | attested: optional; other kinds: absent | string | At most 256 bytes; its scope hash (§5.2) MUST equal `scope` |
| `issuerName` | attested: optional; other kinds: absent | string | At most 64 bytes; self-declared by the producer (§10.3) |
| `statement` | claimed: optional; other kinds: absent | object | `id` (the Design Credits statement id; `claimScope(id)` (§6) MUST equal `scope`) and `uris` of the statement's envelope |
| `cohort` | optional | string | A cohort name, such as a contest round or a year, at most 64 bytes, chosen by the producer of the metadata; display only (§10.1 item 6) |
| `agent` | subject agent: optional; otherwise absent | object | `registry` (`eip155:<chainId>:<address>`) and `agentId` (decimal string) (§7) |

Text members are UTF-8 in Unicode Normalization Form C and MUST NOT contain control characters (U+0000–U+001F, U+007F–U+009F) or any code point with the property `Default_Ignorable_Code_Point` or `Bidi_Control` in Unicode 15.1.0 (the rule of `displayName` in `TAP-draft-design-credits`, restated here). Hashes are `0x` + 64 lowercase hex digits; numbers are JSON integers between 0 and 2^53 − 1.

1. Every value that the credential record holds MUST equal the record as `credentialOf` returns it; where they differ, the record prevails. A member marked "absent" for a kind makes the metadata of that kind invalid, and so does `tap.edition` (§3.2).
2. Status MUST NOT appear in metadata: members of `credential` named `status`, `revoked`, `expired` or `superseded` make the metadata invalid. Anywhere in the document, including ERC-721 `attributes` (by `trait_type`) and nested objects, a member or attribute whose name or meaning is forbidden by §2 item 3 makes the metadata invalid; names such as `value`, `price`, `yield`, `share`, `allocation`, `airdrop`, `reward`, `points`, `weight`, `tier`, `multiplier`, `bonus`, `payout`, `eligibility` or `entitlement`, in any language or spelling, are examples, not a complete list. The member `value` of an ERC-721 attribute entry is part of that format and is judged by its `trait_type`. The member `tap.pod` (`TAP-draft-pod-attributes`) is exempt: its names, such as `bonus`, `multiplier` and `verifWeight`, describe the accounting of the mining contract, and that TAP's non-entitlement rules (its §7) apply to it. The exemption covers the member `tap.pod` only: ERC-721 attributes that repeat its facts are judged like any other attribute. This item applies to every other part of the document.
3. For a proven credential, `tap.netlist.latch` MUST be 0 and `tap.netlist.nand` at most `spec.maxGates`, and `tap.netlist.structuralHash` SHOULD be present.
4. Tools MUST ignore members they do not know, except that they MUST reject metadata that item 2 makes invalid, judging names by meaning and not only by the examples listed, and MUST reject metadata whose text, such as `description`, states or suggests what §2 item 3 forbids. Machine checks, including the reference check and the vectors, cover member names only; text is a matter of tool judgement (Test Cases).

Example (informative; the proven credential of the scenario in `vectors.json`, URIs shortened):

```json
{
  "v": 1, "kind": "proven", "subject": "account",
  "contract": {"chainId": 31337, "address": "0x00000000000000000000000000000000000000c1"},
  "issuer": "0x243d1e8bc2c6aee4bf41136cb139010bb6a20f08",
  "scope": "0xe56510eca6a8ec58dabdec3ed6b77cc1bcbd8cf99f6fa60edab6a8bb1b092b4f",
  "issuedAt": 2000, "expiresAt": 0,
  "spec": {"id": "0xe56510eca6a8ec58dabdec3ed6b77cc1bcbd8cf99f6fa60edab6a8bb1b092b4f",
           "nIn": 2, "nOut": 1, "target": "0xd33c6800252db2f67a985dbb4a7d7a68c0babd8b03d2f95bfea65d836990dd2e",
           "maxGates": 4, "unique": true, "series": "0x…", "info": {"sha256": "0x…", "uris": ["https://…"]}}
}
```

### 10. Display rules

These rules apply to every tool that displays credentials or reports them to others.

#### 10.1 All credentials

1. A tool MUST show the kind of every credential with the labels of §10.2–§10.4 (or the same words in its language), together with the credential contract's chain and address, and MUST NOT display credentials of different kinds in a style that makes them look alike.
2. A tool MUST read the status from the contract at a recent block and MUST show any status other than active. It MUST NOT show a revoked, superseded or expired credential as active, and SHOULD link a superseded credential to its replacement and a replacement to the token it replaces. It SHOULD show a pending proven rebind (§4.7) to the holder of the old token.
3. A tool MUST NOT present a credential, or a count of credentials, as an entitlement to any payment or allocation (§2), and MUST NOT add up or rank credentials of different kinds.
4. A tool MUST NOT treat the kind a contract reports as true merely because the contract reports it. It SHOULD restrict the labels of §10.2 to contracts whose runtime code it has verified to implement this TAP (for example by comparing with a known build of the reference implementation), and otherwise MUST add "unverified contract".
5. Where a tool shows a TAP-721 conformance level (`TAP-draft-netlist-bound-nft` §7.4), it MUST show "L0 (metadata only)" for every credential, as TAP-721 §8.1 requires, and MUST add "metadata can change" unless it has established by the code check of item 4 that the contract fixes `tokenURI` at mint (§3.2); a fixed `tokenURI` is not a freeze in the sense of TAP-721 §7.2 and does not change the level. It MAY add "artifact recorded by the credential contract" next to it after checking that `netlistHashOf(tokenId)` equals `tap.netlist.sha256`. It MUST NOT show a credential as L1 or as "verified on chain" in the sense of TAP-721 §7.4. A tool MUST decide whether a contract implements `ITapNetlistNFT` by ERC-165, not by the presence of functions with its selectors (§8.5), and MUST read a credential's artifact through `netlistHashOf`, not from the set of stored files.
6. `cohort` is chosen by the producer of the metadata. A tool MAY show it as a label, MUST NOT present it as the endorsement of any organiser, contest or foundation, and MUST NOT style it as part of the kind label.

#### 10.2 Proven

1. A tool MUST fetch the artifact file, check its hash, and recompute the checks of §4.6 items 4–6 against `specOf(scope)` before labelling the credential "Proven: passes its specification". A tool that has not done so MUST label it "Proven per contract (not re-checked)".
2. A tool MUST show the specification's registrant as the account that defined the specification, MUST show `maxGates`, and SHOULD show the description fixed by `infoHash`.
3. A tool MUST NOT describe a proven credential as proving who designed the netlist: the recipient revealed a file that passed. When a series is not `unique`, many holders can hold credentials for the same design.
4. A tool MUST NOT describe a credential of a `unique` specification as proving an original design (§4.6).

#### 10.3 Attested

1. The label MUST say that the credential is attested and by whom: the issuer address, in full or one action away, for example "Attested by 0x12…ab (issuer identity not verified)".
2. `issuerName` and `scopeLabel` MAY be shown only for attested credentials, only next to the issuer address and marked as self-declared; a tool MUST NOT replace the address by a name or show a name with a mark of verification, unless the tool itself has established the link by means it names.
3. A tool SHOULD show `expiresAt` when it is not zero.

#### 10.4 Claimed

The label MUST be "Self-claimed" (or the same words in the tool's language). A tool MUST NOT display a claimed credential in the style of a proven or attested one, follows §6 for any statement it carries, and follows `TAP-draft-design-credits` §6.2 for displaying that statement.

#### 10.5 Agents and personal data

1. A tool MUST show the subject `agent` and follows §7 item 3 for any agent identity link.
2. Credentials are public and permanent. A tool SHOULD offer holders a view that hides renounced and revoked credentials from casual display, and SHOULD stop showing `issuerName`, `scopeLabel` and evidence documents of renounced credentials.

## Rationale

**ERC-721 with ERC-5192, not ERC-4973.** ERC-4973 (account-bound tokens, still in Review) requires that tokens do not report the ERC-721 interface; TAP-721 tokens are ERC-721 tokens, so the two cannot be combined. ERC-5192 is Final, adds one function and two events to ERC-721, and is already recognised by wallets. Its consent model is taken from ERC-4973's idea that the receiving account must agree, implemented here by requiring the recipient to send the transaction (§3.6).

**ERC-5484 not required.** ERC-5484 adds a burn-authorisation value fixed at issuance. Under this TAP only the holder can burn, for every kind (§3.7), and issuers revoke by status instead of burning, which keeps a visible record. A contract could implement ERC-5484 with `OwnerOnly` for every token without conflict; requiring it would add an interface without adding information (Open questions).

**Status instead of issuer burns.** Burning a revoked credential would erase the fact that it was issued and revoked, which readers may need; a status flag keeps both. Expiry is computed from the block time, so nobody has to send a transaction for a credential to expire. Because status is read from the contract and the metadata never changes, the contract emits no ERC-4906 event: a `MetadataUpdate` would announce a change that cannot happen.

**Recipient-sent transactions as consent.** A signature-based consent scheme allows gasless issuance but needs one more signed type and makes spam a matter of relayer policy. Requiring the recipient to send the commit, the redemption, the claim or the rebind makes unsolicited credentials impossible by construction and works for contract accounts and agents. A relayed path can be added later (Open questions).

**Kind is fixed by the issuance path.** A contract mints proven credentials only through §4 and attested ones only through §5, so the kind in the record describes how the token was minted, not what someone says about it. Tools can still be lied to by a contract that only pretends to follow this TAP, which is why §10.1 item 4 ties the labels to verified contract code and §10.2 asks tools to re-run the check themselves.

**Exhaustive checks by truth-table hash.** Comparing a hash of the full truth table lets a registrant commit to a function without publishing an implementation, and lets every wallet re-check a credential with the same few lines of code. The column layout, most significant bit first, lets a contract evaluate 256 input vectors per 256-bit word: one NAND per gate per word.

**Exhaustive only, in version 1.** A proven credential should mean that the contract checked the whole statement. The earlier optimistic mode accepted a netlist unless someone found a counterexample against a public reference; the reference then gave the answer away, refutation could come at any time after acceptance, and one-beat evaluation of the largest admitted files did not fit one transaction. Keeping version 1 to what a contract checks in full makes "proven" a property of the token at its mint, and leaves larger circuits to a design built for them (§4.8).

**Two work bounds, measured.** The cost of a reveal has three parts: evaluating every gate on every 256-lane word (about 150 gas per unit), per-gate costs that do not depend on `nIn` (file check, design key and storing the file as contract code, together about 3,000 gas per gate, which the `+ 20` charges), and writing and hashing the truth-table buffer (about 8 gas per byte). A bound on `max(1, 2^nIn/256) · maxGates` alone, as in an earlier draft, admitted specifications with thousands of outputs whose buffer alone needed megabytes of memory, and specifications with many gates on few inputs whose per-gate costs exceeded a transaction. With the two bounds of §4.4 item 2, every corner the reference contract admits reveals in at most 11.8 million gas of execution, measured with Foundry (`SoulboundGas.t.sol`, each specification in its own `unique` series, so that the design-key record of §4.6 is included): 16 inputs, 16 outputs, 237 gates: 11,781,572 gas; 14 inputs, 64 outputs, 780 gates: 11,137,269; 9 inputs, 2,048 outputs, 2,978 gates: 11,087,930; 8 inputs, 3,120 outputs, 3,120 gates: 10,976,589. Calldata adds at most about 240,000 gas, so every reveal fits the 16,777,216-gas transaction limit of EIP-7825 with room to spare. Storing a valid file of the maximum 49,152 bytes (three code chunks) with `storeNetlist` costs 12,516,900 gas, and claiming it 12,680,600. Bounds are published (`checkBounds`, `specOf`) because a tool should know before registering whether a specification will be accepted.

**Commit-reveal with the recipient inside the commitment, recorded per committer.** Committing before revealing stops anyone from copying an answer seen in the mempool or in an earlier reveal of the same round. Putting the recipient and the subject inside the commitment, and accepting a reveal only for a commitment recorded by that recipient, means that a revealed commitment cannot be claimed by someone else, while anyone can pay for the reveal. An earlier draft recorded each commitment once, for whoever sent it first, so that copying a pending commit transaction locked its sender out of the round; recording commitments per committer makes such copies harmless.

**Design keys instead of on-chain structural hashes.** The structural hash needs liveness analysis, merging, depth sorting and a canonical file, which is expensive on chain. For combinational files the ordered labels of the outputs already determine the merged structure: a structural label of TAP-draft-netlist-structural-hash §4.2 is a hash of the label's whole input cone, so two files have equal output labels exactly when their merged structures are isomorphic with the same ordered inputs and outputs, which is the characterisation of equal structural hashes (§8 there). `test_soulbound.py` checks this equivalence on random files and their random renumberings. Renamed copies, input swaps, dead gates and duplicated gates are rejected; function-preserving rewrites such as double negation are not, which a tight `maxGates` limits.

**Duplicates across rounds only.** Many people find the same netlist for small functions on their own; the Design Credits draft records 132 identical four-gate XOR circuits on BNB Smart Chain. Within one round every submission was committed before any was revealed, so equal designs are independent or shared off chain, which no contract can tell apart. Across rounds, an earlier answer is public, and accepting a renamed copy of it would reward reading instead of designing. `unique` is therefore a property of a specification and a series, not of the kind. Every reveal of a series records its design key, so that a `unique` round also rejects answers of earlier rounds that were not `unique`. Together with non-overlapping rounds this makes the rule depend only on what was public before the next round began.

**One credential per account and specification.** Without this rule an account could collect many credentials for one task by submitting variants, or by having credentials of other accounts rebound to it, which inflates any count built on credentials. The rule therefore also binds rebinding (§4.7).

**Attestations bound to one contract.** Design Credits statements are chain-agnostic because they are only displayed. An attestation is redeemed by a contract into a token, so the domain includes the chain id and the contract, and replay elsewhere is impossible. The issuer is inside the message for the same reason Design Credits puts the signer there: an ERC-1271 approval for one account cannot be presented for another account with the same owner. The attestation's `issuedAt` is recorded because it is what the issuer signed; a redemption cannot predate it.

**Key signatures before ERC-1271.** Under EIP-7702 an externally owned account can carry delegated code. Asking such an account's code first would let the delegation decide whether the account's own key signature counts; recovering the key first keeps key signatures valid and asks the code only when the signature is not a key signature for that address. Accepting `v` in {0, 1, 27, 28} matches Design Credits, so that one signing tool serves both.

**Rebinding instead of transfer or social recovery.** A transfer function, even restricted, would let credentials be sold. A recovery account chosen by the holder could also be sold. Re-issue by the party that already decides what the credential means (the issuer, or a recovery authority named in the specification before anyone committed) keeps the trust model of the kind and leaves a visible link. For proven credentials the authority did not decide what passes, so its power is limited by a delay during which the old key can veto; a holder that really lost its key cannot veto, and one whose key still works can stop a rebind it did not ask for. A request lapses if it is not completed within a delay after it became ready, and a newer signed request replaces an older one, so that a mistaken request that nobody completes cannot block recovery for good, while every request that can be completed has given the old key a full delay to veto it.

**One kind per query.** A query that returned proven, attested and claimed credentials as one list would invite readers to count them as equals, which is the confusion this TAP exists to prevent. Requiring a kind in `credentialsOf`, and hashing claimed scopes apart from specification ids, means that no single call returns a self-claimed token in the place of a proven one.

**Agents as accounts.** Binding an agent credential to an ERC-8004 identity would make it follow the identity token when that token is transferred, and the ERC-8004 draft clears the agent wallet on transfer precisely because control changes. Binding to the operating account and treating the registry link as a checked hint keeps the credential soulbound. Because ERC-8004 is a Draft, §7 names no function of it.

**A neutral query and no payouts.** A common query keeps readers from reimplementing one per contract. Weights are policy, which belongs to whoever adopts it; keeping it out of the standard keeps the standard usable by readers with different positions, and keeps the credential itself free of any promise.

**Standards type.** The TAP defines contract interfaces with ERC-165 identifiers, hashes that independent contracts and wallets must compute identically, and rules for tools; that is a Standards TAP under TAP-01 §3.

**Requires.** TAP-02 defines the netlist semantics that truth tables and design keys evaluate (§4.1–§4.3). `TAP-draft-netlist-bound-nft` defines `tapnet/1`, the netlist hash and the metadata this TAP extends. `TAP-draft-design-credits` defines the statements a claimed credential can carry, their verification and revocation (§6) and their display (§10.4). ERC-721, ERC-165 and ERC-5192 define the token; EIP-712 the attestation encoding; ERC-1271 contract issuers and authorities. `TAP-draft-netlist-structural-hash`, `TAP-draft-pod-attributes`, `TAP-draft-large-netlists`, EIP-7702, EIP-7825 and ERC-8004 are referenced for comparisons, an exemption and measurements; nothing required depends on them: the label function of the structural-hash draft is restated in §4.3, and the character rule of the Design Credits draft in §9.

## Backwards Compatibility

This TAP adds a new kind of contract and a member of TAP-721 metadata; it changes no existing contract. Wallets that know ERC-721 show credentials as NFTs; wallets that know ERC-5192 show them as soulbound.

Credentials bind their netlist at mint, so they conform to TAP-721 at L0 and expose the netlist hash through their own interface (§3.2). A proposed amendment to TAP-721, not yet merged, adds a conformance path for such contracts: the mint-bound profile of `TAP-draft-netlist-bound-nft` §8.2 ("Mint-bound collections"), under which a contract that records each token's netlist hash once, at mint, and never changes it, may implement `ITapNetlistNFT` without a manifest. Credential contracts do not use it: the profile is part of L1, which requires ERC-4906, and §3.2 forbids ERC-4906 for credentials (Open question 1). This draft cites that section and does not restate it.

The same amendment states in TAP-721 §6.4 that collections without a manifest do not form editions and that their metadata must not contain `tap.edition`, which §3.2 already requires of credentials, and lists `tap.credential` among the members of `tap` that other drafts use.

This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`) and is submitted after it. TAP-721 is the requested number of the core draft; if editors assign another, this draft takes that number: every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, is replaced by it.

## Test Cases

`assets/tap-draft-soulbound-credentials/vectors.json` (format `tap-soulbound-credentials-vectors/1`) is generated by `make_vectors.py` in the same directory and is reproducible byte for byte; its SHA-256 is `f33709c7e436ba68d89df9adb60f3251172397d82800ab2a0b2592a8f2a64e9b`. Private keys in it are `keccak256("tap-soulbound test key <n>")`, marked `testOnly`, and must never be used for anything else. The EIP-712 domain of the vectors uses chain id 31337 and contract `0x00000000000000000000000000000000000000c1`. Sections:

- `interfaces`: the ERC-165 identifiers of §8.5, every function selector and every event topic;
- `eip712`: the domain, the domain separator `0x755b328ff65f3428bb3f6e2e59f1e83ad5ac34b67e98e431204365d3c1392b92`, and the encodeType strings and type hashes of §5.1;
- `files`: ten netlist files (XOR and its renumbered, input-swapped, dead-gate and double-negation variants, AND, a half adder, 16-input parity, an 8-bit adder, and 24-input parity) with metrics, netlist hash, design key, structural hash and, for up to 16 inputs, truth-table hash;
- `truthTables`: hashes computed from functions, and the exact bytes of three small truth tables (§4.2 bit order);
- `designKeyPairs`: every pair of files with equal pins, showing that design-key equality equals structural-hash equality;
- `specs`, `bounds`, `specChecks`: specifications with their bytes and ids; the reference bounds of §4.4 item 2 with worked examples; and specifications that break each registration rule, including both work bounds;
- `commitments`, `submissions`: commitments and content checks (accepted, too many gates, wrong function, pin mismatch);
- `attestations`, `rebind`, `rebindToHolder`, `rebindVetoed`, `rebindLapsed`, `rebindReplacement`, `rebindReplacement2`: signed attestations (account, agent, re-issue, wrong signer, a high-s variant and a `v` ∈ {0, 1} variant) and six signed `Rebind` messages;
- `claimStatements`: a claim scope (§6) and Design Credits statements carried by a claim, with the display each must get (consistent, mismatch, revoked);
- `scenario`: a sequence of registrations, commits (including a copied commitment that no longer blocks its owner), reveals, rebind requests, vetoes and completions (including a lapsed request, a replaced request and a replacement that restarts the delay), claims, redemptions, revocations and renouncements on the executable model, with every expected error, the final status of tokens 1–7 at two times and `credentialsOf` queries, including rejected queries without a kind and pages whose cursor crosses a renounced token;
- `metadata`: valid and invalid `tap.credential` members and documents with the expected error, including forbidden names outside `credential` and in ERC-721 attributes, `tap.edition`, a `tap.pod` member with mining names (exempt, valid) and the same name repeated in ERC-721 attributes (not exempt), `cohort`, and a document whose `description` promises rewards, which the machine check accepts and which carries a note that a tool must reject it (tool judgement: the machine check covers names only);
- `differential`: 74 random combinational files (the second review's generator, seed 2026), stressing up to 9 inputs with many outputs, 12, 15 and 16 inputs, and files whose every gate is an output, each with its design key and truth-table hash.

The Foundry tests replay the static vectors and the whole scenario against the Solidity reference implementation, compare its truth-table hash and design key with the `differential` section, measure the reveal of every corner of the work bounds, and include both reviews' attack tests as regression tests that must fail to attack.

## Reference Implementation

In this repository, under `assets/tap-draft-soulbound-credentials/`:

- `assets/tap-draft-soulbound-credentials/soulbound.py` (MIT, Python 3.9+, standard library only): truth tables by bit-sliced evaluation, design keys, specification ids and work bounds, commitments, submission checks, claim scopes and the display of Design Credits statements carried by claims, EIP-712 types and signature checks, the metadata check, display labels, interface identifiers, and an executable model of the reference contract; `make_vectors.py` writes `vectors.json`; `test_soulbound.py` checks the vectors, the equivalence of design keys and structural hashes on random files, bit-sliced against TAP-02 evaluation, commitments per committer, the series record of design keys, lapsed and replaced rebind requests, cursors after a renounce and accumulating attested credentials, and cross-checks signatures with `eth_account` and selectors with Foundry `cast` when installed. `canon.py`, `tapnft.py`, `tap02_reference.py` and `credits.py` are copied unchanged from the TAP-721 family and the Design Credits draft (origin and SHA-256 in the folder's README), so that the folder runs on its own.
- `assets/tap-draft-soulbound-credentials/contracts/src/SoulboundNetlistCredential.sol` (MIT, Solidity 0.8.28): all four interfaces, with no owner, no upgrade path, no fees and a base URI fixed at deployment; files are stored as contract code, as in the TAP-721 reference store. `assets/tap-draft-soulbound-credentials/contracts/src/TapCredentialCheck.sol`: the bit-sliced truth-table hash and the design key. `assets/tap-draft-soulbound-credentials/contracts/test/`: Foundry tests (they read `../vectors.json`; forge-std v1.17.0 is installed separately, as the folder's README describes), including the scenario, the differential test, the gas corners of the work bounds, ERC-1271 and EIP-7702 issuers, and the attack regressions of both reviews. `ERC721Min.sol`, `IERC4906.sol` and `TapNetlistCheck.sol` are copied unchanged from the TAP-721 reference contracts; the credential contract overrides `supportsInterface` so that it does not report ERC-4906, and emits no ERC-4906 event (§3.2).
- The same folder, including `contracts/`, is held at a fixed commit in [BruceLanLan/TAP-721, commit `a39f30b538e723e918bf9c3bb2998ee95f8e2f1a`](https://github.com/BruceLanLan/TAP-721/tree/a39f30b538e723e918bf9c3bb2998ee95f8e2f1a) under `assets/tap-draft-soulbound-credentials/` (byte-identical).

## Deployments

This TAP depends on no deployed contract. Anyone may deploy a credential contract; tools decide which contract code they recognise (§10.1 item 4). The reference contract is not deployed yet; a testnet deployment of it, with read-only steps to verify its address, code hash and interface identifiers, will be added to this section before Review.

## Security Considerations

- **Fake proven labels.** Any contract can return kind 1. Tools tie labels to verified code and re-run the checks (§10.1, §10.2); a credential whose contract is not recognised is shown as such.
- **Weak specifications.** A registrant can define a trivial task or a generous gate budget, and anyone can register specifications. The registrant is shown, `infoHash` fixes the description, and readers decide whose specifications they value. A proven credential proves what the specification says, no more.
- **Front-running commits.** Commitments are public in the mempool. Because they are recorded per committer (§4.5), copying a pending commit transaction records a commitment for the copier only; it cannot block the original sender, and it cannot be revealed for the copier because the recipient is inside the commitment.
- **Front-running reveals.** A reveal names its recipient inside the commitment, so a copied reveal transaction mints to the same recipient. A front-runner could only pay the recipient's gas.
- **Copying.** Commit-reveal prevents copying within a round; `unique` rejects renamed copies of earlier rounds' answers in the same series only; function-preserving rewrites escape the design key and are limited only by `maxGates` (§4.6). Answers shared off chain before a round closes cannot be detected.
- **Sybil accounts.** One person can control many accounts and obtain a proven credential with each, or attest to itself. Soulbinding stops trading, not multiplication.
- **Issuer key compromise.** A stolen issuer key can sign attestations and revoke them. Issuers should use contract accounts whose signers can be rotated; a compromised EOA issuer should be treated as untrusted from the time of compromise, which a tool can only learn off chain.
- **Issuer re-issue power.** An issuer can re-issue any of its active or expired attested credentials to any account that redeems the new attestation, at once and without a veto (§5.6). This is a transfer in effect if the issuer is corrupt or its key is stolen. It follows from the attested trust model: the issuer already decides what its credentials mean. Issuers should publish their re-issue policy, and tools should show the link to the replaced token.
- **Recovery authority abuse.** A recovery authority can request a replacement for any account that asks. The authority is named in the specification before any commit, rebind requests are visible on chain, a holder with a working key can veto during the delay (§4.7), and specifications without an authority have no such path. A holder that has lost its key cannot veto, so the delay protects only holders who watch their credentials; tools should alert holders to pending requests (§10.1 item 2). A request that nobody completes lapses, and a new request replaces an older one with a fresh delay (§4.7), so tools should alert holders to every new request, not only the first.
- **Contract issuers change their minds.** ERC-1271 approvals are checked at redemption; a contract issuer can later change which digests it approves, which affects only unredeemed attestations. Revocation is explicit (§5.5).
- **EIP-7702 accounts.** An account with delegated code is accepted by its key signature first (§5.3). A delegation that approves digests under ERC-1271 can additionally sign for the account; the account's owner chose that code.
- **Selector overlap with TAP-721.** `netlistHashOf`, `netlistFile` and `storeNetlist` have the selectors of `ITapNetlistNFT`. A tool that probes for functions instead of ERC-165 could take a credential contract for an L1 collection, and could read a stored file as a token's content. Here `storeNetlist` accepts any valid file, while under TAP-721 it accepts only known netlist hashes. Tools decide conformance by ERC-165 and read a credential's artifact only through `netlistHashOf` (§10.1 item 5).
- **Gas griefing.** Reveals evaluate netlists. Specifications are bounded at registration (§4.4 item 2) so that every admitted reveal fits one transaction; files are bounded at 49,152 bytes; `storeNetlist` stores only valid files, paid for by the caller. `inspect` in the reference implementation is a convenience for off-chain calls and is not bounded.
- **Timestamps.** Windows and the rebind delay use block timestamps, which block producers can shift by seconds; windows should be long compared with that.
- **Privacy.** Credentials link an address to skills, contests, contributions and agents permanently. Renouncing burns the token but cannot erase history or archived metadata. Issuers should keep personal data out of evidence documents and scope labels, or publish only their hashes; holders who want separation should use separate accounts.
- **Reliance on credentials.** A credential is not evidence that different credentials belong to different people; any commitment made on the basis of credentials is the committer's own.

### Open questions

1. Should credential contracts implement the mint-bound profile of TAP-721 §8.2 and report `ITapNetlistNFT` (L1)? That requires ERC-4906, which §3.2 forbids today, and a `frozen()` as that profile defines it (Backwards Compatibility).
2. Should a relayed, gasless consent path (an EIP-712 `Consent` signed by the recipient) be added?
3. Should contracts also implement ERC-5484 with `OwnerOnly`, for wallets that read it?
4. Should a later version add a sequential or large-netlist interface based on the dispute game of `TAP-draft-large-netlists` (§4.8)?
5. Should the rebind delay be a field of the specification instead of a constant of the contract?
6. Should the TAP define a registry of recognised credential contract code hashes, or leave that to tools?
7. Should agent credentials record the agent registry link on chain (and re-check it on every status read), instead of in metadata?

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).
