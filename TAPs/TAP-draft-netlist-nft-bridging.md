---
tap: TBD
title: Moving Netlist-Bound NFTs between TapeOut chains
description: A lock-and-mint bridge for netlist-bound ERC-721 tokens across the TapeOut chains, with one payload format carried over LayerZero V2, the TAP-10 hub, or both at once.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/66
status: Draft
type: Standards
created: 2026-10-18
requires: TAP-10, TAP-draft-netlist-bound-nft, ERC-165, ERC-721, ERC-4906, EIP-712, EIP-7702, LayerZero V2 EndpointV2 (deployed bytecode, code hashes in Deployments)
license: CC0-1.0
---

<!-- `requires`: `TAP-draft-netlist-bound-nft` is TAP-721, the requested number of the core draft; if editors assign another, this draft takes that number. -->

# TAP-TBD: Moving Netlist-Bound NFTs between TapeOut chains

## Summary

This TAP extends TAP-721 (Netlist-Bound NFTs) so that the owner of a TAP-721 token can move it from the chain where it was created to another TapeOut chain and back, with its netlist and image, while only one usable copy exists at any time.

## Abstract

This TAP is an extension of TAP-721 (Netlist-Bound NFTs, `TAP-draft-netlist-bound-nft`): it adds cross-chain transfer of TAP-721 tokens and changes nothing in TAP-721 itself. A TAP-721 token lives in one ERC-721 contract on one chain of the TAP-10 chain table, its **home chain**. This TAP specifies how such a token moves to the other TapeOut chains: a **gateway** on the home chain locks the token in escrow, and a **mirror** on each other chain mints a token with the same id, which it burns again when the token goes back home; tokens always pass through the home chain (hub-and-spoke), so the gateway knows on which chain each token is. Mirrors are ERC-721 contracts that also serve the token's netlist hash, image hash and manifest hash, and accept the netlist file itself, so that a game on any chain can read the circuit. The TAP fixes the collection key, a 320-byte payload, its message id, the endpoint state machine, and an adapter interface that hides the message layer. LayerZero V2, which TapeOut already uses for its rig bridge, is profiled normatively; a profile for the TAP-10 DeWEB hub, whose cross-chain verification is still open, is given as information. Each route uses one of two policies: `ONE` (one layer delivers) or `ALL` (every listed layer must deliver the identical payload before anything happens).

## Motivation

TapeOut runs on BNB Smart Chain, Base and X Layer (TAP-10 §2.1). Collections are created on one of them: TapeCode-Test1, the collection that motivates TAP-721, is on X Layer, while Proof-of-Design mining and most circuit tools are on BNB Smart Chain. Holders and game builders want a token to be usable where the activity is, without giving up the original.

TapeOut has already solved this for one kind of asset. Its rig bridge moves mining rigs from BNB Smart Chain to X Layer over LayerZero V2: a vault on BNB Smart Chain (`0x48D43345656f0f9510dC3c06CBa99dFf597617C2`) holds each rig in its own escrow, and a voucher contract on X Layer (`0x9cfc959cd42B2e1d39a0d850c528210E818AE520`) mints a token that can be redeemed back. That design is specific to rigs and is not a standard: other collections cannot reuse it, it carries no netlist data, and it is bound to one message layer.

A standard is needed for three reasons:

- **Legacy collections cannot change.** TapeCode-Test1 is deployed, its supply is minted, and its only mutable state is a base URI. A bridge that requires the collection to burn and mint (as LayerZero's ONFT721 does in its native form) cannot serve it. Lock-and-mint works with any ERC-721, unchanged.
- **The netlist must travel with the token.** A mirrored token is only useful to circuit games if the remote chain can tell which netlist it carries. The payload therefore carries the netlist, image and manifest hashes, and the mirror accepts the matching netlist file permissionlessly.
- **The message layer is a trust choice.** LayerZero V2 is in production for TapeOut today; the TAP-10 hub is TapeOut's own messaging layer but stores messages only on the sending chain. Collections need one payload and one endpoint behaviour regardless of the layer, and collections that do not want to rely on one layer need the option to require two independent layers.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

Items marked **[Open]** are undecided; they are listed under *Open questions* at the end of Security Considerations.

### 1. Terms and notation

| Term | Meaning |
|---|---|
| Home chain, home collection | The chain (TAP-10 §2.1) and the ERC-721 contract where the collection was created |
| Data source | A contract implementing `ITapNetlistNFT` (TAP-721 §8.2) whose `collection()` is the home collection: the collection itself, or its companion (TAP-721 §8.3). OPTIONAL |
| Endpoint | The gateway or a mirror |
| Gateway | The endpoint on the home chain. Holds departed tokens in escrow |
| Mirror | The endpoint on any other TapeOut chain. An ERC-721 that mints arriving tokens and burns departing ones |
| Adapter | A contract that carries payloads between endpoints over one message layer (§8) |
| Message layer | A cross-chain transport: LayerZero V2 (§9), or the TAP-10 hub with a verifier (§10, informative) |
| Route | The configuration of an endpoint towards one other chain: policy, adapter list, peer endpoint (§5.1) |
| Peer | The endpoint contract on the other chain of a route |
| Payload | The 320-byte message of §4 |
| Source endpoint | The endpoint that sent a payload; the adapter identifies it from the authenticated remote adapter (§8.2) |
| Message id | `keccak256(sourceEndpoint ‖ payload)`, the source endpoint as 20 bytes (§4.1) |
| Live token | A token that exists outside escrow: held by an account in the home collection, or minted on a mirror |

Notation: `‖` is byte concatenation. Integers in byte layouts are big-endian. `abi.encode` is the Solidity ABI encoding. Chain ids are EIP-155 chain ids from the TAP-10 chain table; the TapeOut chains are 56 (BNB Smart Chain), 8453 (Base) and 196 (X Layer).

### 2. Invariant

For every token id of a collection, at most one live token exists across all TapeOut chains. Every departure takes the token out of circulation (escrow on the home chain, burn on a mirror) in the same transaction that sends the payload; every arrival puts it back (release on the home chain, mint on a mirror) only after the route's policy (§7) is satisfied for that payload. A token arrives on a chain at most once per message id.

Tokens move home → mirror and mirror → home only (hub-and-spoke); a move from one mirror to another is two transfers through the home chain. The gateway records the chain each escrowed token departed to, and only a message from that chain can release it (§5.2). Native collections that burn instead of escrowing are out of scope of this version.

### 3. Collection key

```
collectionKey = keccak256(abi.encode("TAP-NFT collection v1", uint64 homeChainId, address homeContract))
```

The string is ABI-encoded as a dynamic `string`. Every endpoint of a collection MUST return the same `collectionKey()` and `homeChainId()`, and MUST reject payloads with another collection key. For TapeCode-Test1 (`homeChainId` 196, `homeContract` `0x0e91460d6823c711643e650a9a4c0cc21de41614`) the key is `0x8755cf608e750f9bd55ba6ac4c0e655dffffc199774518f82624273f5217b4bd`.

### 4. Payload

#### 4.1 Layout

```
payload   = abi.encode(uint8 version, bytes32 collectionKey, uint256 tokenId, address to,
                       bytes32 netlistHash, bytes32 imageHash, bytes32 manifestHash,
                       uint64 srcChainId, uint64 dstChainId, uint64 nonce)
messageId = keccak256(sourceEndpoint ‖ payload)        sourceEndpoint: the sending endpoint's 20-byte address
```

| Offset | Word | Content |
|---|---|---|
| `0x000` | version | `1` |
| `0x020` | collectionKey | §3 |
| `0x040` | tokenId | The token id in the home collection |
| `0x060` | to | Recipient on the destination chain, left-padded with 12 zero bytes; non-zero |
| `0x080` | netlistHash | `tapnet/1` SHA-256 bound to the token (TAP-721 §2.3); zero if none |
| `0x0a0` | imageHash | Image SHA-256 bound to the token; zero if none |
| `0x0c0` | manifestHash | The collection's manifest SHA-256; zero if none |
| `0x0e0` | srcChainId | Chain id of the sending endpoint |
| `0x100` | dstChainId | Chain id of the receiving endpoint |
| `0x120` | nonce | The sending endpoint's outgoing counter, starting at 0 and increased by 1 per departure |

The payload is exactly 320 bytes. A receiving endpoint MUST reject (revert with `BadPayload()`) a payload unless: its length is 320; the version word equals 1; the `to` word is non-zero and its upper 96 bits are zero; the upper 192 bits of each of the three `uint64` words are zero. One payload therefore has exactly one encoding. The sending endpoint computes the message id with its own address, the receiving endpoint with the source endpoint that its adapter authenticated (§8.2). Because `(source endpoint, nonce)` never repeats, message ids do not repeat, including when an endpoint is replaced and its successor starts again at nonce 0.

#### 4.2 Hashes

- A gateway with a data source MUST fill `netlistHash`, `imageHash` and `manifestHash` from `netlistHashOf(tokenId)`, `imageHashOf(tokenId)` and `manifestHash()` of the data source at departure, and MUST revert (`NotBound(uint256)`) if the data source's `masterSeed()` is non-zero (including the all-ones value of a collection without reveal, TAP-721 §8.2 item 2), the token is covered by the manifest, and either `netlistHashOf(tokenId)` is zero while the data source has a pool with the netlist field, or `imageHashOf(tokenId)` is zero while it has a pool with the image field (fields as in `pools()`, TAP-721 §5.2): after the reveal, a covered token is bound (TAP-721 §8.2) before it departs. A data source that does not report `ITapNetlistTokenSet` through ERC-165, or whose `tokenSetHash()` is zero, is in range mode, and a token is covered if its id lies inside the data source's `tokenRange()`. Otherwise it is in set mode (TAP-721 §5.4), where `tokenRange()` returns `(0, count)` and is not a range, and the gateway MUST NOT use it for this test: the gateway MUST revert (`NotBound`) unless `tokenAt(0)` succeeds, which shows that the token set file has been recorded on chain (recording it is permissionless in the reference implementation); a token is then covered if `indexOf(tokenId)` does not revert. A token that is not covered can never be bound and departs with zero hashes. A gateway without a data source sends zeros.
- A mirror MUST send the values it holds for the token (§5.3).
- A gateway MUST ignore the hashes of arriving payloads: the home data source is authoritative.

#### 4.3 Worked example

TapeCode-Test1 #7 leaves X Layer for BNB Smart Chain, recipient `0x00000000000000000000000000000000000000b0`, first departure of a gateway at the example address `0x00000000000000000000000000000000000a0196` (nonce 0). The netlist is the 23-byte `tapnet/1` file `5441504e45540100000000020000000100000002000003` (one NAND); the image and manifest hashes are SHA-256 of the ASCII strings `example image` and `example manifest`. (Example values; this vector is `home-to-remote` in Test Cases.)

```
0x000  0000000000000000000000000000000000000000000000000000000000000001   version
0x020  8755cf608e750f9bd55ba6ac4c0e655dffffc199774518f82624273f5217b4bd   collectionKey
0x040  0000000000000000000000000000000000000000000000000000000000000007   tokenId
0x060  00000000000000000000000000000000000000000000000000000000000000b0   to
0x080  b6438e95fafa86bad91caa97b0893dbd520bb71b94cf053a7b677858c9609be8   netlistHash
0x0a0  0d85f5af1e0dfa09503f0bdb179ab8f37c4225b43d442a3a91e59c3c849bc99e   imageHash
0x0c0  89333bc71f02c647533ab52e592ad22c609728f12eabff6fda0920109db40401   manifestHash
0x0e0  00000000000000000000000000000000000000000000000000000000000000c4   srcChainId 196
0x100  0000000000000000000000000000000000000000000000000000000000000038   dstChainId 56
0x120  0000000000000000000000000000000000000000000000000000000000000000   nonce 0

keccak256(payload) = 0x11c7027b724893ce8f921c02e44af216e59a0878b57502bfe8c6edd032487497
messageId          = 0xc4ced4c2227e9504511e68531d1975140f510e3a0d19b5bcd44db3f33e681e58
```

### 5. Endpoints

#### 5.1 Common behaviour

Every endpoint implements `ITapBridgeEndpoint` and `ITapBridgeTransfer`, reports both through ERC-165, and records:

- `departed[messageId]`: set when the endpoint sends a payload;
- `executed[messageId]`: set when a payload takes effect;
- `confirmedBy[messageId][adapter]`: set when an adapter delivers a payload on an `ALL` route. It is not recorded on a `ONE` route, where `executed` is the only record.

**Routes.** For each other chain, a route holds a policy (`NONE` = 0, `ONE` = 1, `ALL` = 2), an ordered adapter list and the peer endpoint. `setRoute(chainId, policy, adapters, peer)` MUST revert (`NotOwner()`, `Sealed()` or `BadRoute()`) unless: the caller is the owner and routes are not sealed; `chainId` is neither 0 nor the local chain; `policy` is 0, 1 or 2; for `NONE`, the adapter list is empty; for `ONE`, it has exactly one entry; for `ALL`, it has 2 to 8 entries; entries are non-zero and distinct; for `ONE` and `ALL`, `peer` is non-zero; on a mirror, `chainId` is the home chain. `NONE` closes the route in both directions. There is no other policy value.

**Sealing.** `sealRoutes()` MUST revert unless the caller is the owner, at least one route is open, and every adapter listed on any route reports `adapterSealed()` = true (`AdapterNotSealed(address)`, §8.3). It then sets `routesSealed`, clears the owner and emits `RoutesSealed`; this is irreversible. A sealed endpoint therefore also guarantees that none of its adapters can change how it authenticates messages.

**Departure.** `bridge(tokenId, dstChainId, to, contractRecipientOk, options)` MUST, in this order:

1. revert if `to` is zero; if `to` has code on the local chain other than an EIP-7702 delegation designator (exactly 23 bytes starting `0xef0100`) and `contractRecipientOk` is false (`ContractRecipient(address)`); if the route is `NONE`; or if `to` is the route's peer or the endpoint itself (`EndpointRecipient(address)`);
2. revert unless `options` is empty or has one entry per adapter of the route;
3. take the token out of circulation (§5.2, §5.3), which reverts unless the caller is the token's owner, an operator approved for all of the owner's tokens, or the account approved for the token;
4. build the payload with the next nonce, set `departed`, emit `Departed`;
5. call `send` on every adapter of the route, in route order, with the fee that adapter's `quote` returns (§12), and refund any excess value to the caller.

`quoteBridge` returns the total and per-adapter fees for the same arguments.

**Arrival.** `receivePayload(srcChainId, srcEndpoint, payload)` MUST, in this order:

1. revert if the route to `srcChainId` is `NONE`, if the caller is not in its adapter list, or if `srcEndpoint` is not the route's `peer`;
2. decode the payload strictly (§4.1) and revert unless `srcChainId` equals the payload's `srcChainId`, the payload's `dstChainId` equals the local chain id, its `collectionKey` equals the endpoint's, and its `to` is not the endpoint itself;
3. compute `messageId = keccak256(srcEndpoint ‖ payload)` and revert (`Replay(bytes32)`) if `executed[messageId]` is set;
4. emit `Confirmed(messageId, caller)`;
5. on an `ALL` route: revert if `confirmedBy[messageId][caller]` is set, otherwise set it; then return without effect unless `confirmedBy[messageId][a]` is set for every adapter `a` in the route's **current** adapter list;
6. set `executed[messageId]`, put the token back into circulation for `to` (§5.2, §5.3), and emit `Arrived`.

The local chain id is `block.chainid` at construction.

**Resending.** `resend(payload, adapterIndex, options)` is permissionless. It MUST revert unless `departed[keccak256(endpoint ‖ payload)]` is set, and MUST send the payload unchanged through adapter `adapterIndex` of the current route to the payload's destination, charging that adapter's quote and refunding the rest. Because arrival is keyed by message id and adapter, a resend can complete a pending `ALL` message but never makes a payload take effect twice.

**Interfaces.** Each selector below is the first 4 bytes of `keccak256` of the function signature, and each ERC-165 identifier is the XOR of the selectors of that interface's functions; all are also in `vectors.json` (Test Cases).

`ITapBridgeEndpoint` (identifier `0x3d6a52e3`):

| Function | Selector |
|---|---|
| `receivePayload(uint64 srcChainId, address srcEndpoint, bytes payload)` | `0xcb4d10e1` |
| `collectionKey() returns (bytes32)` | `0x11305740` |
| `homeChainId() returns (uint64)` | `0xef126967` |
| `route(uint64 chainId) returns (uint8 policy, address[] adapters, address peer)` (`policy` is an enum, `uint8` in the ABI) | `0x9e38705d` |
| `routesSealed() returns (bool)` | `0x963d0c78` |

`ITapBridgeEndpoint` also declares these events:

| Event | topic0 |
|---|---|
| `Departed(bytes32 indexed messageId, uint256 indexed tokenId, uint64 dstChainId, address to)` | `0xb5be151363c3a3ff877f22f1a2b29b927c303c39455f28969c828e77a284c564` |
| `Confirmed(bytes32 indexed messageId, address indexed adapter)` | `0xd4964a7cd99f5c1fa8f2420fb5e1d3bd26eadf16e2658cf2e29a67dfda38601e` |
| `Arrived(bytes32 indexed messageId, uint256 indexed tokenId, uint64 srcChainId, address to)` | `0x8b93f26fdf44f4f9532c9bccd40895f7bf298adc1902c7a86eb995ee36ba736a` |

`ITapBridgeTransfer` (identifier `0xdbc2d1d3`):

| Function | Selector |
|---|---|
| `quoteBridge(uint256 tokenId, uint64 dstChainId, address to, bytes[] options) returns (uint256 total, uint256[] fees)` | `0xaed4dd7d` |
| `bridge(uint256 tokenId, uint64 dstChainId, address to, bool contractRecipientOk, bytes[] options) payable returns (bytes32 messageId)` | `0x1ddf49a0` |
| `resend(bytes payload, uint256 adapterIndex, bytes options) payable returns (bytes32 transportId)` | `0x8dbe72e9` |
| `departed(bytes32) returns (bool)` | `0x2084e062` |
| `executed(bytes32) returns (bool)` | `0xa9fcfb33` |
| `confirmedBy(bytes32, address) returns (bool)` | `0x34a5b4aa` |
| `nextNonce() returns (uint64)` | `0xd69c3d30` |
| `setRoute(uint64 chainId, uint8 policy, address[] adapters, address peer)` | `0x9a50a738` |
| `sealRoutes()` | `0x14660214` |

`ITapBridgeTransfer` declares `RouteSet(uint64 indexed chainId, uint8 policy, address[] adapters, address peer)` (`0xa555875b3d8c275c0366501b23edd5240ebc78f5374d6b9983540a89b2eedcbd`) and `RoutesSealed()` (`0x8b978f73eaca99332cb4c63aaaca48701bb356b32365e7e247fe9a0e65b5c370`).

**Errors.** Endpoints revert with these errors where this section and §5.2–§5.3 name them; tools MAY rely on them to tell causes apart (§9, *Retry*):

| Error | Selector | Raised when |
|---|---|---|
| `BadPayload()` | `0x442dd415` | §4.1 decoding fails |
| `RouteClosed(uint64)` | `0x0122f114` | The route is `NONE` |
| `NotAdapter(address)` | `0x08b4a225` | The caller of `receivePayload` is not listed on the route |
| `WrongPeer(address)` | `0x70260226` | `srcEndpoint` is not the route's peer |
| `WrongSource()` / `WrongDestination()` / `WrongCollection()` | `0x83efd75c` / `0xef94f60c` / `0x747d07f2` | Payload chain ids or collection key do not match |
| `Replay(bytes32)` | `0x7e7b2e50` | The message id already executed |
| `AlreadyConfirmed(bytes32,address)` | `0x900bdd46` | The same adapter delivers twice on an `ALL` route |
| `NotDeparted(bytes32)` | `0x830e142b` | `resend` of a payload this endpoint did not send |
| `ZeroRecipient()` / `ContractRecipient(address)` / `EndpointRecipient(address)` | `0xd27b4443` / `0xc9cd32cd` / `0x777e60a5` | Recipient checks of departure and arrival |
| `BadOptions()` / `InsufficientFee(uint256,uint256)` / `RefundFailed()` | `0x26864a7a` / `0xa458261b` / `0xf0c49d44` | Options count, fee, refund |
| `NotOwner()` / `Sealed()` / `BadRoute()` / `AdapterNotSealed(address)` | `0x30cd7471` / `0x1b2d71eb` / `0xc4c321d1` / `0x4fec0d65` | Route configuration and sealing |
| `NotAuthorized()` / `AlreadyEscrowed(uint256)` / `NotEscrowed(uint256)` / `NotOnRoute(uint256,uint64)` / `EscrowFailed(uint256)` / `NotBound(uint256)` | `0xea8e4eb5` / `0xc826d283` / `0xa64a2c0c` / `0x62caffe3` / `0x054f9d0d` / `0xd0078a0a` | Gateway (§5.2, §4.2) |
| `ERC721NotAuthorized(address,uint256)` / `AlreadyLive(uint256)` / `OutOfRange(uint256)` / `ManifestConflict(bytes32,bytes32)` / `NotHomeCollection()` | `0xb226c90b` / `0x6adc3ab8` / `0x6f2fb69e` / `0xda3bad61` / `0xbbfa1ada` | Mirror (§5.3) |

#### 5.2 Gateway

A gateway is deployed with the home collection and an optional data source; its `homeChainId` is the local chain. The constructor MUST revert if a data source is given whose `collection()` is not the home collection.

- **Departure:** the gateway MUST revert (`AlreadyEscrowed`) if the token is already in its escrow, whatever the collection's approval semantics; after the caller check of §5.1 it calls `transferFrom(owner, gateway, tokenId)` on the home collection, MUST revert unless `ownerOf(tokenId)` is then the gateway, and records the destination chain as the token's location (`locationOf(uint256) returns (uint64)`, `0x6b8b81b8`; 0 = not escrowed). The owner therefore approves the gateway on the home collection before the first departure.
- **Arrival:** the gateway MUST revert (`NotEscrowed`) unless the token has a recorded location and is held by the gateway, and (`NotOnRoute`) unless the payload's `srcChainId` equals that location; it clears the record and calls `transferFrom(gateway, to, tokenId)`. It MUST NOT use `safeTransferFrom` (a recipient contract cannot refuse a returning token).
- The gateway MUST NOT implement `onERC721Received`, so that `safeTransferFrom` into escrow fails; a plain `transferFrom` to the gateway outside `bridge` locks the token with no way out, and wallets SHOULD warn against it.
- The gateway has no function that moves an escrowed token other than arrival.

**Discovering a collection's endpoints.** The home collection's token metadata (TAP-721 §7.1) MAY contain `"bridge": {"chainId": <home chain id>, "gateway": "<lowercase address>"}` inside its `tap` object. A client that finds it MUST check that the gateway's `homeChainId()` equals the chain of the collection and that its `collectionKey()` equals the key of §3 computed from that chain id and the collection address, before using it. The canonical mirror of the collection on chain `c` is `peer` of the gateway's `route(c)`. Clients MUST NOT accept a mirror that is not reachable this way from the gateway, whatever its name, symbol or collection key.

#### 5.3 Mirror

A mirror is deployed on a chain other than the home chain with `homeChainId`, the home collection address, a name and symbol, a base URI, and the token range `(firstTokenId, supply)` copied from the home collection. `supply` = 0 means that the range is unbounded; this is part of the bridged-copy case of TAP-721 §8.2. A mirror of a collection in set mode (TAP-721 §5.4) MUST be deployed with `supply` = 0, because the data source's `tokenRange()` of `(0, count)` is not the set of covered ids. The mirror implements ERC-721 with the metadata extension, ERC-165, ERC-4906, `ITapBridgeMirror` and the mirror profile of `ITapNetlistNFT` below.

- **Arrival:** the mirror MUST revert (`AlreadyLive`) if the token exists on the mirror, and (`OutOfRange`) if `supply` ≠ 0 and the token id is outside the range. If the payload's `manifestHash` is non-zero: when the mirror's `manifestHash()` is zero it stores it and emits `ManifestCommitted`; when it differs, the mirror MUST revert (`ManifestConflict`). The mirror stores the payload's `netlistHash` and `imageHash` for the token, records a non-zero `netlistHash` as known, mints the token to `to` without calling `onERC721Received`, and emits ERC-4906 `MetadataUpdate(tokenId)`.
- **Departure:** after the caller check of §5.1 the mirror burns the token and sends the hashes it holds. The hashes stay stored after the burn: `netlistHashOf`, `imageHashOf` and `netlistOf` keep returning the values last carried in, while `ownerOf` reverts. A later arrival overwrites them.
- **Netlist files:** `storeNetlist(file)` and its alias `materialize(file)` are permissionless. They MUST revert unless SHA-256(`file`) is a known netlist hash, the file is at most 49,152 bytes long and it is valid `tapnet/1` (TAP-721 §2.2, §8.2 item 4); a stored file is readable through `netlistFile(hash)` and `netlistOf(tokenId)`. Storing is idempotent. The selectors of `storeNetlist(bytes)` (`0xf8b0cc86`), `netlistFile(bytes32)` (`0x5267c429`) and `netlistOf(uint256)` (`0xae502e0b`), and the topics of `ManifestCommitted(bytes32)` (`0x283da7c24290f991388adb4188dab383e865d9edad5d228e8b95805b85bba620`) and `NetlistStored(bytes32,address)` (`0x4095b27949435770a1b733b92eb73b92fb8d0c052ef06cf5db328010d57a64ed`), are those of `ITapNetlistNFT` (TAP-721, Test Cases); `MetadataUpdate(uint256)` is ERC-4906 (`0xf8e1a15aba9398e019f0b49df1a4fde98ee17ae345cb5f6b5e2c27f5033e8ce7`).
- **tokenURI:** `baseURI ‖ decimal tokenId`, or the empty string when the base URI is empty. The base URI is fixed at deployment. The document at a mirror's `tokenURI` MUST be byte-identical to the home collection's document for the same token, which identifies the token by its home identifier (TAP-721 §4.1). A mirror SHOULD NOT be deployed before the home collection's metadata location is final.

**Mirror profile of `ITapNetlistNFT`.** A mirror has no manifest file, pools or reveal of its own. It returns: `collection()` = the mirror itself; `tokenRange()` = the deployed range; `manifestHash()` = the first non-zero manifest hash carried in (never changes once non-zero); `pools()` = empty; `masterSeed()` = 0; `frozen()` = false; `netlistHashOf`, `imageHashOf` = the hashes the token carries (zero while no hash is known for the token), kept after departure. `entryIndexOf` and `bind` MUST revert with the error `NotHomeCollection()` (selector `0xbbfa1ada`). A mirror computes no entry indices; any extension that does MUST derive pool seeds from the home chain id and home collection address (the manifest's `collection`, TAP-721 §6.2), never from the mirror's own. This is the bridged-copy case that TAP-721 §8.2 allows. A mirror reports `ITapNetlistNFT` through ERC-165 together with `ITapBridgeMirror`; a client that finds `ITapBridgeMirror` knows the reveal and the manifest file are on the home chain.

`ITapBridgeMirror` (identifier `0xdba6a55e`):

| Function | Selector |
|---|---|
| `knownNetlist(bytes32 netlistHash) returns (bool)` | `0xd86844a4` |
| `manifestHash() returns (bytes32)` | `0x337f3f32` |
| `materialize(bytes file) returns (bytes32 netlistHash)` | `0x30b1dec8` |

### 6. State machine

Per token id, across all chains:

| State | Where the live token is | Leaves the state by |
|---|---|---|
| Home | An account on the home chain | `bridge` at the gateway → In flight |
| In flight (home → c) | Nowhere; the original is in the gateway's escrow, location `c` | Arrival accepted at the mirror on `c` → Mirrored on `c` |
| Mirrored on `c` | An account on chain `c` | `bridge` at the mirror → In flight (c → home) |
| In flight (c → home) | Nowhere; burned on `c`, the original still escrowed with location `c` | Arrival from `c` accepted at the gateway → Home |

Per message id, at a receiving endpoint:

| State | Meaning | Next |
|---|---|---|
| Unknown | Nothing delivered | A listed adapter delivers → Executed (`ONE`), or Pending (`ALL`) |
| Pending (`ALL` only) | Some, not all, adapters of the current route confirmed | The last missing adapter delivers → Executed |
| Executed | The token was released or minted | Terminal; any delivery reverts `Replay` |

A delivery that reverts (wrong peer, wrong source, `AlreadyLive`, `ManifestConflict`, `NotEscrowed`, …) leaves the message where it was. Whether it can be retried is a property of the message layer (§9, §10).

### 7. Policies

- **`ONE`** (RECOMMENDED default): the single listed adapter's delivery takes effect immediately.
- **`ALL`**: every listed adapter must deliver the byte-identical payload; the token is released or minted on the last confirmation. Adapters that deliver payloads differing in any byte confirm different message ids, and neither takes effect.
- There is no `ANY` policy (any one of several adapters suffices).

**Stuck adapters.** An endpoint MUST NOT fall back from `ALL` to fewer adapters on its own, and has no timeout. If one adapter of an `ALL` route never delivers, the message stays Pending and the token stays out of circulation. Recovery, in order of preference:

1. The message layer's own retry: re-execution of a failed LayerZero delivery by anyone (§9), or new attester signatures for a hub message (§10).
2. Before `sealRoutes()`: the owner replaces the stuck adapter by another one on both endpoints, and anyone calls `resend` through the new adapter. This relies on the owner, as every pre-seal change does.
3. After `sealRoutes()`: only the first path remains. If a layer is permanently gone after sealing, tokens in flight on its `ALL` routes are lost, and no account can recover them.

### 8. Adapters

#### 8.1 Interface

`ITapBridgeAdapter` (identifier `0xaa621a3e`):

| Function | Selector | Behaviour |
|---|---|---|
| `layerId() returns (bytes32)` | `0xd3cf3ef1` | `keccak256` of a label naming the layer and profile version (§9, §10) |
| `quote(uint64 dstChainId, bytes payload, bytes options) returns (uint256)` | `0x49e6cd30` | Native fee for `send` with the same arguments |
| `send(uint64 dstChainId, bytes payload, bytes options, address refundTo) payable returns (bytes32 transportId)` | `0x304be9ff` | Only the adapter's endpoint may call. Transmits the payload, unchanged, to the peer adapter on `dstChainId` |

An adapter serves exactly one endpoint, fixed at deployment, and calls `receivePayload` only on that endpoint.

#### 8.2 Source endpoint

Adapters transport the bare 320-byte payload. Because an adapter serves exactly one endpoint, an authenticated remote adapter identifies the sending endpoint. On receipt, after the layer's own authentication of the remote adapter, an adapter MUST pass the endpoint that this remote adapter serves as `srcEndpoint` to `receivePayload(srcChainId, srcEndpoint, payload)`, and MUST revert if it has no such endpoint configured for `srcChainId`. The configuration is set once per remote chain, together with the peer adapter; exposing it as `remoteEndpoint(uint64 chainId) returns (address)` (`0xf2d88e04`) is RECOMMENDED (the reference adapters do). The endpoint then checks the source endpoint against its route (§5.1), so the route table, not only the adapters' peer tables, decides which contract on the other chain may speak for the collection.

#### 8.3 Adapter seal

An adapter MUST implement `ITapBridgeAdapterSealed` (identifier `0xceebf7ce`): `adapterSealed() returns (bool)` (`0xceebf7ce`), and the event `AdapterSealed()` (`0x16ce24d3a7b82addfa23f273f6be525d4610ab33551f22d0ca872db8e9ffbe9e`). It returns true only once no account can change anything that affects how the adapter authenticates incoming messages or which endpoint it reports as their source: peers, remote endpoints, the remote container of the hub profile, and, for LayerZero, the EndpointV2 delegate (which chooses message libraries, DVNs and confirmations). Once true it never returns false. In the reference adapters, `seal()` (`0x3fb27b85`, owner only, irreversible) runs the profile's freeze, clears the owner and emits `AdapterSealed`. An adapter's owner MUST NOT be able to renounce other than through sealing (`transferOwnership(address(0))` reverts with `ZeroOwner()`, `0x9905827b`), so an adapter without an owner always reports sealed. A LayerZero adapter MUST NOT report sealed while any configured remote eid follows the endpoint owner's defaults (§9, *Seal*).

After sealing, nothing that affects authentication remains configurable. What stays possible: anyone can call `quote`, `resend` through the endpoint, re-execute a stored LayerZero delivery, and relay a hub message with valid signatures; the fees charged by message-layer workers can change, because they are set by those workers.

### 9. LayerZero V2 profile

`layerId` = `keccak256("TAP-NFT adapter LayerZeroV2 v1")` = `0x117f05b8b59be0e82e43c9302d01f46e149b6a74d295ff09c2df95de7ff7ff97`.

The adapter is an OApp integrated directly against EndpointV2 (`0x1a44076050125825900e736c501f859c50fE728c` on all three chains, Deployments):

| Item | Requirement |
|---|---|
| Endpoint ids | BNB Smart Chain 56 ↔ eid **30102**; Base 8453 ↔ eid **30184**; X Layer 196 ↔ eid **30274** |
| Peers | `setPeer(uint64 chainId, uint32 eid, bytes32 peer, address remoteEndpoint)` (`0x2e50800b`), owner only, once per chain: it MUST revert if the chain id, the eid or the peer slot is already set. `peer` is the remote adapter, left-padded to 32 bytes; `remoteEndpoint` is the endpoint it serves (§8.2) |
| Sending | `EndpointV2.send(MessagingParams(dstEid, peer, payload, options, false), refundTo)` (`0x2637a450`) with the value passed by the endpoint; fees in the native coin only. `quote` calls `EndpointV2.quote(params, adapter)` (`0xddc28c58`) and returns `nativeFee` |
| Options | The caller's `options` if non-empty; otherwise `0x0003 ‖ 0x01 ‖ uint16(17) ‖ 0x01 ‖ uint128(gas)` (type-3 options, executor worker, `lzReceive` gas). With 400,000 gas: `0x00030100110100000000000000000000000000061a80`. The default gas SHOULD be at least 400,000 (a first arrival on a mirror costs about 236,000, Reference Implementation) |
| Receiving | `lzReceive(Origin origin, bytes32 guid, bytes message, address executor, bytes extraData)` (`0x13137d65`) MUST revert unless the caller is EndpointV2, `msg.value` is 0, and `peers[origin.srcEid]` is non-zero and equals `origin.sender`; then §8.2 with `srcChainId` = the chain bound to `origin.srcEid`; the LayerZero message is the payload itself |
| Path | `allowInitializePath(Origin)` (`0xff7bd03d`) returns `peers[srcEid] == sender` (and false for a zero sender); `nextNonce(uint32, bytes32)` (`0x7d25a05e`) returns 0 (unordered delivery) |
| Delegate | The constructor calls `EndpointV2.setDelegate(delegate)` (`0xca5eb5e1`); the owner may change it until the adapter is sealed. The delegate chooses message libraries, DVNs and confirmations for the adapter on EndpointV2. Sealing (§8.3) MUST set the delegate to zero |
| Seal | `seal()` MUST revert (`NotPinned(uint32 eid)`, `0xd2f23d72`) unless at least one remote eid is configured and, for every configured eid: `EndpointV2.isDefaultSendLibrary(adapter, eid)` (`0xdc93c8a2`) is false; `EndpointV2.getReceiveLibrary(adapter, eid)` (`0x402f8468`) returns a non-zero library with `isDefault` false; `EndpointV2.receiveLibraryTimeout(adapter, eid)` (`0xef667aa1`) has no expiry above the current block; and that library's `getAppUlnConfig(adapter, eid)` (`0x39e3f938`, the adapter's own ReceiveUln302 config, not merged with defaults) has `confirmations` neither 0 (default) nor `type(uint64).max` (ULN302's NIL value, zero confirmations), and `requiredDVNCount` neither 0 (default) nor 255 (NIL, no required DVNs) and equal to the length of `requiredDVNs`. A sealed adapter therefore no longer depends on the endpoint owner's default libraries or default receive configuration |

**DVN configuration.** Before the adapter is sealed, the delegate MUST pin the send and receive libraries and the receive configuration (the seal checks this), SHOULD require at least two DVNs operated by different parties, and SHOULD set block confirmations at least to these counts: BNB Smart Chain 15, Base 64, X Layer 300. (Measured on 2026-10-17 between 17:45 and 17:46 UTC, three samples per chain: the `finalized` tag of BNB Smart Chain lagged the latest block by 2 blocks; the `safe` tag lagged by 11 to 34 blocks on Base and by 39 to 245 on X Layer. The counts add a margin and, for X Layer, equal TAP-10's maximum pin lag.) Sealing freezes this configuration, including any DVN that later stops working.

**Retry.** A delivery that reverts in `lzReceive` stays stored by EndpointV2, and anyone can execute it again once its cause is gone. A `ManifestConflict` never goes away, so such a message is permanently failed. `AlreadyLive` cannot arise between honest endpoints (a repeated message for an executed id reverts `Replay` instead); it means that a layer delivered a second, different message for a live token, and is a sign of compromise, not a condition to retry.

### 10. TAP-10 hub profile (informative) [Open]

This section is informative in this version. An adapter that follows it is not a conforming adapter of this TAP until a verifier for hub messages is specified; it is included so that implementations of `ALL(LayerZero, hub)` agree on the format in the meantime.

The TAP-10 hub (`0xe61A9C7213a6Aa616C246a2B569e555B417b25ee`, the same address on every chain, TAP-10 §13.2) records a message only on the sending chain. A destination contract cannot read another chain's hub, so this profile needs a verifier. The section describes the source side and one verifier, a fixed attester set.

`layerId` = `keccak256("TAP-NFT adapter TAP-10 hub relay v1")` = `0x52d641b576bf4d57ffe8457eeb80d8684348265b309a824d5c2a72ad11584ce2`.

**Source side.**

- The adapter holds a circuit NFT whose container is opened (TAP-10 §13.4), set once with `setCircuit(address circuits, uint256 circuitId)` (`0x6672d2d3`), which reverts (`NotCircuitHolder()`, `0x094c282c`) unless `ownerOf(circuitId)` is the adapter. That container is the author of every message the adapter writes. The adapter has no function that transfers the circuit away.
- Per remote chain, set once with `setRemote(uint64 chainId, address adapter, address container, address remoteEndpoint)` (`0x66bc31da`): the remote adapter, the container that writes for it on its chain, and the endpoint it serves (§8.2).
- `send` reverts if `msg.value` ≠ 0, and calls `hub.send(circuits, circuitId, to, ref, payload)` (`0xa181b579`) with `to = uint32(0) ‖ uint64(dstChainId) ‖ remote container`, the TAP-10 §12.1 endpoint id of the remote adapter's container, and `ref` = the message id (§4.1). It returns the TAP-10 §17 message id of the entry as `transportId`. `quote` returns 0: the hub charges no fee, and the relayer pays destination gas.

**Attester verifier.** The destination adapter is deployed with an attester list in strictly ascending address order and a threshold `K` (1 ≤ K ≤ N); neither can change. Anyone may call

```
deliver(uint64 srcChainId, uint256 outboxIndex, bytes32 ref, bytes payload, bytes signatures)    0x1645190f
```

which reverts unless: `remoteContainer[srcChainId]` is set; `(srcChainId, outboxIndex)` was not delivered before; `ref == keccak256(remoteEndpoint[srcChainId] ‖ payload)`; and `signatures` is exactly `K` concatenated 65-byte `r ‖ s ‖ v` signatures with `v` ∈ {27, 28}, `s` ≤ secp256k1n/2, recovering to listed attesters in strictly ascending order, over the EIP-712 hash of

```
EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)
  name = "TAP-NFT Hub Relay", version = "1", chainId = destination chain, verifyingContract = destination adapter
HubMessage(uint64 srcChainId,address hub,address fromContainer,uint256 outboxIndex,bytes32 digest)
  hub = the hub address, fromContainer = remoteContainer[srcChainId],
  digest = keccak256(ref ‖ keccak256(payload))          (TAP-10 §13.6)
```

It then marks `(srcChainId, outboxIndex)` delivered and continues with §8.2. `hubMessageHash(uint64, address, uint256, bytes32)` (`0xbd48a881`) returns the hash to sign; the domain separator is recomputed if `block.chainid` changes.

An attester signs only after reading, under TAP-10 strict agreement, the outbox entry `outboxIndex` of `fromContainer` on the source chain's hub at a block at or below the confirmed height of that chain's finality tag (TAP-10 §17), and checking that the entry's digest equals `digest`, that the entry's `to` equals the endpoint id of the destination adapter's container, and that its `Sent` log carries `ref` and `payload` (TAP-10 §18.3). Attesters also check that the source hub is accepted and the processor implementation unchanged (TAP-10 §13.8), and that the circuit was held by the source adapter when the entry was written.

**What an on-chain verifier would need.** The destination would have to verify, without trusted parties, that the source hub's storage holds the outbox entry: a trusted source block hash on the destination chain (a light client or validity proof of the source chain, or of Ethereum for Base and X Layer plus their L1 settlement), and a storage proof (`eth_getProof`) of the hub's `deweb.hub.v1` namespace (TAP-10 §13.3). Such a verifier would replace the attester check inside `deliver` and keep everything else.

### 11. Roles and sealing

| Contract | Deployer | Owner before sealing | Owner powers | After sealing |
|---|---|---|---|---|
| Gateway, mirror | Anyone; the owner is a constructor argument | The account named at deployment | `setRoute` | `sealRoutes()` (only once every listed adapter is sealed) sets `routesSealed` and clears the owner; no power remains |
| LayerZero adapter | Anyone | The account named at deployment | `setPeer` once per chain, `setDelegate`, `transferOwnership`, `seal` | `seal()` (only once libraries and receive configuration are pinned for every configured eid) sets the EndpointV2 delegate to zero and clears the owner; no power remains |
| Hub relay adapter | Anyone | The account named at deployment | `setCircuit` once, `setRemote` once per chain, `transferOwnership`, `seal` | `seal()` clears the owner; the attester set is immutable from deployment |

No endpoint or adapter is upgradeable, and none has a pause, a rescue function or a way to move escrowed tokens. An endpoint SHOULD be sealed once its routes are configured and tested. Clients SHOULD show whether a collection's endpoints are sealed and which policy each route uses.

### 12. Fees

The caller of `bridge` and `resend` pays every adapter's native fee in one transaction, as quoted by the adapter at that moment; excess value is refunded to the caller, and too little reverts the whole call. LayerZero refunds its own excess to `refundTo` (the caller). Endpoints charge nothing of their own and hold no balance between transactions. Destination execution for LayerZero is paid through the options; for the hub profile it is paid by whoever calls `deliver` **[Open]**.

## Rationale

- **Relationship to TAP-721.** This TAP is a separate extension rather than a section of TAP-721 because its security rests on message layers that can still be upgraded: LayerZero V2 endpoint configuration, DVNs and executors, and the TAP-10 hub, whose cross-chain verification is still open. A TAP that depends on upgradeable contracts stays Candidate until they are sealed (TAP-01 §5.1); inside TAP-721, that dependency would hold back the whole standard, although TAP-721 collections need none of it to be minted, revealed or verified on their home chain. Kept apart, TAP-721 can advance on its own, this TAP can advance once routes and adapters are sealed (§8.3, §11), and a bridge never changes a TAP-721 collection on its home chain.
- **Lock-and-mint, with the original as the only source of truth.** Burning on the home chain would require the collection to cooperate, which legacy collections such as TapeCode-Test1 cannot do. Escrow works with any ERC-721 and leaves the home collection, its supply and its marketplaces untouched; a token that comes home is the original object.
- **Why not ONFT721 as is, and the alternative this draft leaves open.** LayerZero's ONFT721 is a library pattern of one message layer, not an ERC. Its adapter form (`ONFT721Adapter`) escrows an unchanged ERC-721 exactly as the gateway does, and a mirror could be an `ONFT721` subclass. A cross-chain review of this draft recommends that design for any deployment: the three hashes appended to the standard ONFT message, the mirror profile of §5.3 and `materialize` kept as they are, at least three required DVNs from different operators in place of the `ALL` policy, and hub-and-spoke routing with per-route accounting at the home adapter. It gains stock LayerZero tooling (wiring and configuration checks), a much smaller new audit surface (a few hundred lines over audited library code instead of the custom endpoint and adapters), and the same shape as TapeOut's own production bridge, a stock `OFTAdapter`. It loses the layer-independent `ALL` policy and the adapter interface: it is LayerZero-only, and a second, independent layer could not be added later without a new standard. This draft specifies the custom design so that the comparison is concrete, adopts hub-and-spoke routing and per-route accounting from the review, and invites the TAPs discussion to choose between the two. No deployment is planned for TapeCode-Test1 v1.
- **Why not ERC-7786.** ERC-7786 defines a generic cross-chain messaging gateway interface. This TAP does not use it for `ITapBridgeAdapter` because ERC-7786 is a Draft, and its attributes model fixes neither the payload nor a policy across several adapters, which are the parts this TAP has to pin down.
- **Why hashes in the payload.** A mirror can then answer `netlistHashOf` and accept the netlist file without trusting anyone beyond the message layer, and games on every chain read the same circuit. Image and manifest hashes cost two words and let a mirrored token be displayed and checked like the original.
- **Why the message id includes the source endpoint.** Endpoints can be replaced before sealing, and a replacement starts at nonce 0. Without the source endpoint, its first payloads could be byte-identical to messages its predecessor sent, and the destination would reject them as replays while the token is already escrowed or burned. Hashing the authenticated source endpoint with the payload keeps the payload format fixed at 320 bytes.
- **Why no `ANY` policy.** With several layers of which any one suffices, an attacker needs to break only the weakest; `ANY` would be strictly less secure than `ONE` on the best layer. `ALL` makes an attacker break every layer, at the price of liveness: one stalled layer stalls the route.
- **Why no automatic fallback from `ALL`.** A fallback that triggers after a timeout would let an attacker who controls one layer and can stall the other mint alone. Recovery is therefore explicit (§7) and, after sealing, limited to what the layers themselves offer.
- **Why both layers.** LayerZero V2 is in production for TapeOut today (the rig bridge) and is the only layer that delivers messages without new infrastructure. The TAP-10 hub is TapeOut's own layer and its trust is independent of LayerZero, but it needs a verifier, so its profile is informative for now. `ONE` is the default; `ALL` exists for routes that must not trust a single layer.
- **Why the endpoint checks the source endpoint.** Adapters authenticate the remote adapter; `receivePayload` also takes the source endpoint, so the endpoint's route table, sealed with the routes, is the final word on which contract may speak for the collection, and a misconfigured adapter cannot redirect a route on its own.
- **Why sealing covers the adapters.** An owner who can change routes, peers or the LayerZero delegate can make a route deliver forged messages. `sealRoutes()` therefore requires every listed adapter to be sealed first, so that one on-chain flag tells a client that no account keeps such a power. The cost is that adapter failures after sealing cannot be repaired by an owner.
- **Why hub-and-spoke.** With mirror-to-mirror hops, the gateway cannot know where a token is, so a compromise of the weakest route into the gateway could release every escrowed token. Routing every move through the home chain costs a second transfer for a mirror-to-mirror move, which is rare for NFTs, and lets the gateway release a token only on the route it was sent to.
- **Why discovery starts from the home metadata.** The gateway's address has to come from somewhere a holder already trusts; the home collection's own metadata is that place, and it lets any collection use this TAP without a change to this document.
- **Why mirrors keep hashes after a burn.** It keeps `netlistOf` and stored files useful for history and makes a return trip cheaper; `ownerOf` already tells whether the token is present.

## Backwards Compatibility

The home collection is not modified; holders who never bridge see no change. TapeCode-Test1 and other existing ERC-721 collections can use a gateway as they are; their data source, if any, is a companion (TAP-721 §8.3). The rig bridge is not changed by this TAP and does not follow it: rigs are not TAP-721 tokens and the rig vault and voucher keep their own interfaces.

Indexers that index the home collection see departed tokens owned by the gateway; they can resolve the live token through the gateway's `Departed` events and the mirrors' `Arrived` events.

This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`) and is submitted after it. TAP-721 is the requested number of the core draft; if editors assign another, this draft takes that number: every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, is replaced by it.

## Test Cases

`assets/tap-netlist-nft-bridging/vectors.json` (format `tap-netlist-nft-bridging-vectors/2`) is generated by `make_vectors.py` in the same folder (dependency-free Python, its own Keccak-256), and is reproducible byte for byte: `python3 make_vectors.py --check` (SHA-256 `bcfd12c1a2f6d875ce602da32632c260afcd6c5b560a97297044f1f690224f51`). It contains:

- **Collection keys**: TapeCode-Test1 on X Layer, and a BNB Smart Chain example;
- **Valid payloads**, each with its fields, payload bytes, `keccak256(payload)`, an example source endpoint, the message id, the hub `ref` and the hub digest: `home-to-remote` (§4.3), `remote-to-home` (BNB Smart Chain → X Layer, nonce 3), `remote-to-home-unbound` (zero hashes), `extremes` (largest token id, chain ids and nonce);
- **Invalid payloads** that every endpoint rejects (§4.1): length 319 and 321, version 2, a non-canonical version word, a zero `to`, a `to` word with high bits, and each `uint64` word overflowing;
- **LayerZero**: eids, the default option bytes for 400,000 and 300,000 gas, the layer id;
- **Hub relay**: layer id, the `to` endpoint id of an example container, the EIP-712 type hashes, a domain separator, a struct hash and the hash to sign for a fixed message;
- **Interfaces**: the selectors, ERC-165 identifiers, event topics and error selectors listed in this TAP.

The Solidity reference implementation reproduces every vector (`test/bridge/TapBridgeVectors.t.sol`).

Behavioural tests (`test/bridge/TapBridge.t.sol`, `TapBridgeCompanion.t.sol`, three chains simulated in one EVM by switching `block.chainid`): round trips home → remote → home and BNB Smart Chain → home → Base → home, with a mirror-to-mirror route refused; `ONE` over a mock layer, over LayerZero (mock EndpointV2) and over the hub (mock hub with holder check and attester signatures); `ALL(LayerZero, hub)` where either layer alone does not mint and the second confirmation does, in both orders and back home; mismatched payloads across the two adapters of an `ALL` route never execute; the same adapter confirming twice; replay after execution, including after the token left again; wrong LayerZero peer, forged origin, a listed adapter naming a source endpoint that is not the route's peer; an adapter not listed on the route; wrong source, destination and collection; double mint, release of a token not in escrow, and per-route accounting (a token on BNB Smart Chain is not released by a message on the Base route); manifest conflict and out-of-range ids; route validation, adapter sealing (including a LayerZero adapter that cannot seal while any eid follows default libraries, default receive configuration or a receive-library grace period, and rejects ULN302's NIL values) and endpoint sealing; recovery of a stuck `ALL` adapter by replacement and `resend`; fees, refunds and option counts; a contract recipient refused without acknowledgement, accepted with it, and an EIP-7702 account treated as a plain account; the bind-first rule after the reveal and the escrow record; netlist materialization, chunked storage of a 49,016-byte file and `netlistOf` on the mirror; the empty reveal surface of the mirror profile; a TapeCode-Test1-shaped legacy collection (`setBaseURI`, `freezeBaseURI`, no ERC-4906) with the core `TapCompanion` of TAP-721 as data source, through commit, reveal, bind, bridge and materialize. Regression tests from the security review (`test/audit/AuditBridge.t.sol`, `AuditFixes.t.sol` for a token outside the manifest range, which departs with zero hashes, and `AuditPass3.t.sol` for token-set membership and NIL ULN values): an endpoint as recipient, a replaced gateway whose nonce restarts (the legitimate message executes), a collection that keeps approvals after transfer (no second departure of an escrowed token), and adapter sealing (no delegate or peer change after sealing).

The mock EndpointV2 does not run DVN verification or EndpointV2's own nonce and payload-hash bookkeeping, so the replay tests exercise the endpoint contract's guard, which a real EndpointV2 would normally stop earlier. The mock hub does not check that the container is opened.

## Reference Implementation

In this repository, Foundry project `contracts/`, solc 0.8.28, optimizer 10,000 runs, EVM `shanghai`. Before Review (TAP-01 §7.2 item 8), the project will be either moved under `assets/tap-<nn>/` or linked here at a fixed commit of an external repository (CONTRIBUTING §2.4, TAP-01 §6.2).

| Path | Content |
|---|---|
| `src/interfaces/ITapBridge.sol` | `ITapBridgeAdapter`, `ITapBridgeEndpoint` |
| `src/interfaces/ITapBridgeTransfer.sol`, `ITapBridgeMirror.sol`, `ITapBridgeAdapterSealed.sol` | The interfaces of §5.1, §5.3 and §8.3 |
| `src/bridge/TapBridgePayload.sol` | Collection key, payload encoding, strict decoding, message id |
| `src/bridge/TapBridgeEndpoint.sol` | Routes, policies, sealing, replay protection, dispatch, resend |
| `src/bridge/TapGateway.sol` | Home endpoint (escrow) |
| `src/bridge/TapMirror.sol` | Remote endpoint; uses `src/vendor/ERC721Min.sol`, `src/core/TapNetlistStore.sol` and `src/core/TapNetlistCheck.sol` from TAP-721 |
| `src/bridge/TapAdapterBase.sol`, `LayerZeroV2Adapter.sol`, `ILayerZeroEndpointV2Min.sol` | Adapter base (including the seal) and the LayerZero V2 profile, with no LayerZero library dependency |
| `src/bridge/HubRelayAdapter.sol` | The informative hub profile with the attester verifier |
| `test/bridge/`, `test/audit/AuditBridge.t.sol` | Tests and mocks (EndpointV2, hub, mock layer, legacy collection, data source) |

Runtime sizes: gateway 16,114 bytes, mirror 21,345, LayerZero adapter 8,676, hub relay adapter 8,259.

Measured execution gas (Foundry, `gasleft()` around the call; *mock transport that stores nothing*, so the message layer's own cost comes on top):

| Operation | Gas |
|---|---|
| Gateway `bridge` (escrow and location record, three data-source reads, payload, one adapter call) | 206,066 |
| Mirror arrival on a `ONE` route (mint, two hashes, known netlist, manifest on first arrival) | 236,441 |
| Mirror `bridge` (burn, payload) | 152,696 |
| Gateway arrival on a `ONE` route (location check, release) | 127,818 |
| Hub relay `deliver` with 2-of-3 signatures, completing an `ALL` route and minting | 348,317 |
| `materialize`, 23-byte file / 49,016-byte file | 89,479 / 12,355,979 (about 252 gas per byte) |

## Deployments

None of the contracts of this TAP is deployed, and no deployment is planned for TapeCode-Test1 v1. Each endpoint's and adapter's owner is a constructor argument; until a pull request adds an address here, clients accept no deployment as the official endpoints of TapeCode-Test1. This TAP records deployments; it cannot order them.

The TAP depends on the following deployed contracts.

**LayerZero V2 EndpointV2.** **Measured** read-only on 2026-10-17 between 16:19 and 16:43 UTC (`eth_call` and `eth_getStorageAt`, one node per chain, not strict agreement): X Layer blocks 73,484,955–73,486,332 via `rpc.xlayer.tech`, BNB Smart Chain blocks 128,201,222–128,204,265 via `tapeout.net/rpc`, Base blocks 52,732,329–52,733,011 via `mainnet.base.org` (each value read once, at the latest block of its read). The endpoint address, eids and default libraries agree with LayerZero's deployment metadata (`https://metadata.layerzero-api.com/v1/metadata/deployments`, fetched on 2026-10-17 at about 16:19 UTC, SHA-256 `d1898aa5ec6f6fc0af3d31b1cafd50f636b68ca9e0521e1c21f1e0fd164a18f9`), which is the data behind LayerZero's "Deployed Contracts" documentation page.

| Chain (chainId) | EndpointV2 | `eid()` | `owner()` | Code hash | ERC-1967 slot | Default send / receive library (path to the other chains) | Sealed? |
|---|---|---|---|---|---|---|---|
| BNB Smart Chain (56) | `0x1a44076050125825900e736c501f859c50fE728c` | 30102 | `0xEFACCEc3B9661b5ff62418243c013f2F58Ce1350` | `0x5ed1f4ec5f4d6bd5eac1fa92e0fb7474be2607dfc5f3eb82ced1c183b64fbeb9` | 0 (not a proxy) | `0x9F8C645f2D0b2159767Bd6E0839DE4BE49e823DE` / `0xB217266c3A98C8B2709Ee26836C98cf12f6cCEC1` | Not upgradeable; the owner sets default libraries |
| Base (8453) | same | 30184 | `0xa0392d116D71ED3b75086194aBa6De3CD1e39B7E` | `0x086c2e9e37f5bdaf45013882cf40f7a43b35c879302ff1ad4a4010d09b4d7237` | 0 | `0xB5320B0B3a13cC860893E2Bd79FCd7e13484Dda2` / `0xc70AB6f32772f59fBfc23889Caf4Ba3376C84bAf` | as above |
| X Layer (196) | same | 30274 | `0xE590a6730D7a8790E99ce3db11466Acb644c3942` | `0x21c2d567afee99c79aa52beca53380975509c8d5bedd5ff55ff6c5451dec378f` | 0 | `0xe1844c5D63a9543023008D332Bd3d2e6f1FE1043` / `0x2367325334447C5E1E0f1b3a6fB947b262F58312` | as above |

The code hashes differ per chain because the endpoint's eid is an immutable. `nativeToken()` is zero on all three chains (fees in BNB, ETH or OKB). LayerZero eid 30155 is OKXChain (66), a deprecated chain, not X Layer. Default libraries are the endpoint owner's choice at the time of reading and can change; adapters are advised to pin their own (§9).

**TAP-10 DeWEB hub.** `0xe61A9C7213a6Aa616C246a2B569e555B417b25ee` on every chain; implementations, owner and seal status as listed under TAP-10 Deployments (not sealed as of TAP-10's last reading). The informative hub profile also depends on the processor factory and circuit beacon of each chain (TAP-10 §13.4, §13.8), which are not sealed.

**Existing rig bridge (precedent, not a dependency).** BNB Smart Chain vault `0x48D43345656f0f9510dC3c06CBa99dFf597617C2` and X Layer voucher `0x9cfc959cd42B2e1d39a0d850c528210E818AE520`, both upgradeable proxies administered by `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138`, eids 30102 and 30274. Their `endpoint()` returns `0x1a44076050125825900e736c501f859c50fE728c` (read on 2026-10-17, UTC); their peer configuration was not read (`peers(uint32)` reverted on both), and the rig bridge does not include Base.

## Security Considerations

- **Adapter compromise under `ONE`.** Whoever can make the route's single adapter deliver arbitrary payloads can release every escrowed token on the home chain to themselves and mint any token that is not live on a mirror. For LayerZero this means the configured DVNs (and, until the adapter is sealed, its owner and delegate); for the hub profile, `K` attesters. A route is exactly as secure as its one layer.
- **Per-route accounting at the gateway.** The gateway records the chain each escrowed token departed to and releases it only on a message from that chain (§5.2). A compromised route can therefore release only the tokens that are on its chain, and mint on its own mirror only tokens that are not live there. Collections that must not depend on a single layer still use `ALL` (or several required DVNs) on every route.
- **Adapter compromise under `ALL`.** An attacker must control every listed layer for the same payload. A compromised layer alone can only confirm payloads that the other layers never deliver; it can also refuse to deliver, which stalls the route (§7).
- **Configuration that survives sealing.** `sealRoutes()` succeeds only when every listed adapter is sealed (§8.3), and a sealed LayerZero adapter has no delegate and no remote eid that follows default libraries or default receive configuration. The endpoint's own adapter check trusts each adapter's report, so clients recognise only adapters whose code they know (the reference adapters or audited equivalents). Before that, the adapter owner can change the delegate and set missing peers, and so can make a route deliver forged messages; clients treat a collection as sealed only when `routesSealed()` is true.
- **DVN configuration.** A LayerZero adapter that follows the endpoint owner's defaults inherits whatever the owner sets later, including the DVN set. Pinning libraries and requiring at least two independent DVNs before sealing moves that trust to the configuration chosen at sealing, including any DVN that later fails.
- **Stuck messages.** A token in flight is out of circulation until its message executes. Messages that revert at the destination for a permanent reason (`ManifestConflict`) never execute; an `AlreadyLive` revert indicates a compromised or faulty layer (§9). After sealing, there is no owner to repair a route (§7, path 3).
- **Reorganizations and finality.** If the source chain reorganizes after a destination executed a payload, the token can exist twice: the departure is undone at the source while the arrival stands at the destination. LayerZero confirmations (§9) and attester signatures therefore wait for the finality tags of TAP-10 §2.1 (`finalized` on BNB Smart Chain; `safe` on Base and X Layer, whose single sequencers can rewrite unconfirmed blocks). As an observation of current practice, not a requirement: TapeOut's production BEM bridge, which also carries rigs, uses 20 block confirmations in both directions. Read on 2026-10-17 at about 18:32 UTC with `EndpointV2.getConfig(oapp, receiveLibrary, eid, 2)` (and `getAppUlnConfig` on the receive library): the X Layer BEM OFT `0x60e62Efa9405d6873C5deaBD4E6CC91c25363952` receiving from BNB Smart Chain (eid 30102, library `0x2367325334447C5E1E0f1b3a6fB947b262F58312`) returns 20 confirmations, 1 required DVN and 2 of 3 optional DVNs; the BNB Smart Chain `OFTAdapter` `0xa84B8D3893De6e9922f2B29bE1e1b115845F5E72` receiving from X Layer (eid 30274, library `0xB217266c3A98C8B2709Ee26836C98cf12f6cCEC1`) returns 20 confirmations, 2 required DVNs and 1 of 2 optional DVNs. Twenty X Layer blocks are well short of X Layer's `safe` head (39 to 245 blocks behind the latest block when measured, §9), so on the X Layer → BNB Smart Chain path those deliveries rely on the X Layer sequencer not reorganizing.
- **The endpoint owner.** EndpointV2 is not a proxy, but each chain's endpoint has an owner (Deployments) who registers message libraries and sets defaults. Its power over an adapter that pinned its libraries is limited to what those libraries allow; over an adapter that did not, it is complete.
- **Unsealed TapeOut contracts (hub profile).** While the processor factory is not sealed, whoever controls it can replace the processor implementation and write to the hub as any container (TAP-10 Security Considerations), including the adapter's; while the hub is not sealed, its owner can rewrite outbox entries. Attesters who follow TAP-10 §13.8 notice a lasting change but not necessarily a temporary one.
- **Spoofed mirrors and metadata.** Anyone can deploy a contract with the collection's name, symbol, collection key and hashes. Only mirrors reachable from the gateway's routes (§5.2) are genuine, and a mirror's hashes are only as trustworthy as the route's policy. Mirror metadata is the home document, served off chain; tools check images and netlists against the hashes (TAP-721 §4.2).
- **Double mint.** The `AlreadyLive`, `NotEscrowed` and `AlreadyEscrowed` checks stop a second arrival for a token that is live on the same chain and a second departure of an escrowed token, but cannot see other chains. A forged arrival on a chain where the token is not live mints a second live token; preventing it is the job of the policy and the layers.
- **Recipients.** A smart-contract wallet at address `X` on one chain is usually not deployed at `X` on another chain, or is deployed there by someone else; a token sent to it may be unrecoverable or end up with a stranger. This is why `bridge` refuses a recipient that has code on the source chain unless the caller sets `contractRecipientOk` (§5.1), as TapeOut's rig bridge does. The check runs only on the source chain: the destination cannot tell whether `to` is controlled by the sender there, and an address without code on the source chain may still be a contract, or a counterfactual wallet, on the destination. Callers who set the flag, and interfaces that offer it, take that risk explicitly. An endpoint as recipient would hold the token for good, so departure refuses the route's peer and the sending endpoint, and arrival refuses the receiving endpoint.
- **Approvals.** Departure requires the caller to be the owner or approved for the token, in addition to the gateway's approval on the home collection, so a holder who approved the gateway for all tokens cannot have them shipped by a stranger. Marketplaces holding operator approval can bridge a holder's token, as they can transfer it. The escrow record makes the invariant independent of collections that keep per-token approvals after a transfer.
- **Home collection powers.** The gateway's escrow is only as safe as the home collection. A collection whose owner can move or burn tokens, or which is upgradeable, can break the invariant from the home side; clients are advised to show this. TapeCode-Test1's owner can only change and freeze its base URI.
- **Hub relay specifics.** The attesters are a fixed `K`-of-`N` set with no rotation; losing more than `N − K` keys stops the route, and `K` colluding keys break it. Relaying is unpaid, so delivery depends on someone willing to pay destination gas. The `hub` field of the signed message is the destination's hub address, which equals the source's only because the hub has the same address on every chain (TAP-10 §13.2).
- **Linked libraries.** Where a home collection or data source reaches a linked library by DELEGATECALL (for example the evaluation library of TAP-721), that library has full write access to its storage, including the data the gateway reads. Clients verify the linked address in the deployed bytecode against the published library address and code hash before trusting the hashes a gateway carries.
- **Large netlists.** Storing a netlist costs about 252 gas per byte, and mirrors accept files of at most 49,152 bytes (§5.3); a larger file cannot be materialized on a mirror, although its hash still travels.

### Open questions

1. **Hub verifier.** No on-chain way to verify a TAP-10 hub message on another chain exists. Who would run attesters, how many, and how they are replaced (only by deploying a new adapter and changing routes before sealing)? Is a light-client or validity-proof verifier feasible for BNB Smart Chain, Base and X Layer? Until this is settled, §10 stays informative.
2. **Relayer incentive** for the hub profile: unpaid, paid by the sender through the adapter, or paid by attesters.

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).
