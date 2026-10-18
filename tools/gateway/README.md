# TAP-10 server-side HTTPS gateway (reference)

Serves files stored in TapeOut containers (TAP-10 site store, §6–§7) over plain HTTPS. It is meant for clients that
cannot run the browser Service Worker gateway of TAP-10 §8.8, in particular NFT marketplaces that fetch a
`tokenURI` JSON file and its `image` from their own servers.

You can deploy it in two ways. Both use the same core, `core.js`, which has no dependencies (~670 lines):

| Form | Entry | Runtime |
|---|---|---|
| Cloudflare Worker (ES module) | `worker.js` + `wrangler.toml` | Workers (uses `fetch`, `crypto.subtle`) |
| Standalone server | `server.js` | Node 20+ (`node:http`), behind any TLS terminator |

It is read-only. It makes `eth_blockNumber`, `eth_chainId`, `eth_call`, `eth_getStorageAt` and `eth_getCode` calls, and never signs or sends a transaction.

## URL forms

| Form | Example | Notes |
|---|---|---|
| Path form (one stable host) | `https://gw.example.org/1.2.282.tape/meta/1` | First segment is the on-chain name (short name `1.2.282` also accepted). `/1.2.282.tape` redirects to `/1.2.282.tape/` |
| Host label form (TAP-10 §3.3) | `https://1-2-282.gw.example.org/meta/1` | Needs `GATEWAY_DOMAIN` and a wildcard certificate |
| Status JSON | `/.tape/status/1.2.282.tape` (path form), `/.tape/status` (host form) | Resolution, activation, lock state, pinned block, implementations |

`/sw.js` and every `/.tape/…` path are reserved, and site files at those paths are never read (§8.8).

## What one request does

1. The gateway parses the name (§3.1/§3.3). An unknown area code, a leading zero or a value out of range is a 400 `input-error`. The chain comes from the area code: none = BSC, `3` = Base, `2` = X Layer.
2. It pins a block (§5.3). It asks every configured node for `eth_chainId` and `eth_blockNumber`, keeps the lowest head per operator, takes Q = min(2, operators), and pins the Q-th highest head minus 2. If the pin lag is above the chain's max (BSC 400, Base 150, X Layer 300 blocks) the result is `stale-block` (503). A node on the wrong chain gives `wrong-chain` (502).
3. Every read uses default agreement (§5.2). Each JSON-RPC batch (at most 8 calls, because `rpc.xlayer.tech` rejects batches over about 10) goes to every operator. A read is adopted only if at least two operators answered and every answer received is identical. Any disagreement returns **502 `node-disagreement`**, and there is no majority vote. Fewer than two answers returns 503 `unavailable`. A revert counts as an answer and is normalised to a bare `revert`, because nodes differ on whether they include revert data.
4. It applies the site resolution of §6.2, in order:
   - It reads the ERC-1967 slot of `SiteRegistry` and `DomainBinding` and compares it with the accepted implementations hard-coded from TAP-10 Deployments. A mismatch is `store-changed` (502) and nothing is read.
   - `factory.cpuCount`/`cpuAt` gives the processor, `factory.isCPU` checks it, `opener.accountOf` gives the container, `ownerOf` gives the holder, and `opener.isOpened` must be true.
   - The blocklist is checked (§10). A hit returns 451.
   - Activation (§6.3): `isLive(name, container)` OR `isContainerLive(container)`, where a revert counts as false. If neither holds the result is `unpaid` (403), unless `SERVE_UNPAID=1`.
5. It reads the file (§7). It calls `fileInfo`, then `read` for files up to 98,304 bytes or `readRange` segments for larger ones, all at the pinned block. The length must equal the declared size and the SHA-256 must equal the declared hash; otherwise the result is 502 `incomplete`. Files over 8,400,000 bytes return 413. A file whose owner declared no hash (`sha256Hash` = 0) is refused with 502 `no-hash`, because this gateway only serves verified bytes.
6. Path rules (§7.2): strip `?`/`#`, percent-decode, NFC, collapse `//`, and reject control characters and `.`/`..` segments. A path ending in `/` gets `index.html`. Landing order is (a) an exact match, (b) `<path>/index.html` for an extension-less path, (c) `fallbackPath`. **An exact match always wins**, so TapeCode-Test1's `meta/1` (no extension) is served as that file with its stored contentType.
7. The contentType is sanitised (§7.1.6): only `A-Za-z0-9 _ . + / ; = -` and space are kept, the result is cut to 100 characters, and it must start with `type/subtype`, otherwise `application/octet-stream`.

Error and status responses are plain text or JSON. They never echo the requested path and carry `Cache-Control: no-store`.

## Response headers

| Header | Value |
|---|---|
| `x-tape-name`, `x-tape-status`, `x-tape-container`, `x-tape-block`, `x-tape-sha256`, `x-tape-verified` | §8.8 (`x-tape-verified: true` only after the size and SHA-256 check) |
| `ETag` | `"0x<sha256>"`. `If-None-Match` gives 304 |
| `Cache-Control` | `public, max-age=31536000, immutable` when the container is **frozen**, otherwise `public, max-age=60` (§11 caps resolution caching at 60 s) |
| `Access-Control-Allow-Origin: *` | On every response. No credentials are used. `OPTIONS` preflight is answered |
| `Content-Security-Policy: default-src 'none'; sandbox` | On every file. A file opened as a document (HTML, SVG) gets an opaque origin, runs no script and loads nothing. This also covers the path form, where all sites share one host. JSON and images fetched by servers or `<img>` are unaffected |
| `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: cross-origin` | Always |

**Frozen** means that nobody can rewrite the files. The gateway treats a container as frozen in either of two cases. In both, `SiteRegistry.operatorOf(container)` must also be the zero address:

- The circuit's holder is a contract whose `locked()` returns true, and whose `processor()`, `circuitId()` and `container()` match this circuit (`TapContainerLock`, `contracts/src/tools/`).
- The holder is the container itself (self-owned). No writes are possible, but nobody can renew the activation either.

## Configuration

The defaults are hard-coded in `core.js` (`CHAINS`). Contract addresses and accepted implementations come from TAP-10 Deployments and can't be configured. A client must never learn them from a server (§2.2).

| Variable | Meaning | Default |
|---|---|---|
| `GATEWAY_DOMAIN` | Enables the host label form for `*.GATEWAY_DOMAIN` | empty (path form only) |
| `RPC_BNB`, `RPC_BASE`, `RPC_XLAYER` | `operator=url,operator=url` or a JSON array of `{operator,url}`. Nodes with the same operator label count as one | see below |
| `BLOCKLIST` | Text, one container address or on-chain name per line, `#` comments | empty |
| `SERVE_UNPAID` | `1` serves sites whose activation expired | off (official-shell behaviour, §6.3) |
| `SPA_FALLBACK` | `0` disables §7.2 step 4c (`fallbackPath`) | on |
| `RESOLUTION_TTL_MS` | In-memory resolution cache, capped at 60 000 | 15 000 |
| `PORT` | Node only | 8787 |

Default nodes:

| Chain | Operators |
|---|---|
| BSC | `bnbchain` https://bsc-dataseed.bnbchain.org, `publicnode` https://bsc-rpc.publicnode.com |
| Base | `coinbase` https://mainnet.base.org, `publicnode` https://base-rpc.publicnode.com |
| X Layer | `xlayer` https://rpc.xlayer.tech, `okx` https://xlayerrpc.okx.com, `drpc` https://xlayer.drpc.org |

The first two X Layer endpoints are both published by the X Layer/OKX side, and their independence is **not verified**. `drpc` is the clearly independent third operator, so keep it, or add your own node. Never put a node URL that carries an API key in a public file (§5.1). Use `wrangler secret put RPC_XLAYER` for that.

**Turn `SPA_FALLBACK=0` on for NFT metadata.** Container `1.2.282.tape` has a fallback of `index.html`. With the fallback on, a not-yet-uploaded `meta/1` returns that HTML page with status 200, which a marketplace may cache as broken metadata. With the fallback off it returns 404. This was verified live.

## Deploy

**Cloudflare Worker**

```sh
cd tools/gateway
# edit wrangler.toml: GATEWAY_DOMAIN, routes (gw.example.org/* and, for the host form, *.gw.example.org/*), SPA_FALLBACK="0"
npx wrangler deploy
```

The host form needs a wildcard certificate for `*.gw.example.org`. Cloudflare's Advanced Certificate Manager or Total TLS covers one label. If you use the host form, put the gateway domain on the Public Suffix List so that sites do not share cookies (§8.8).

**Node**

```sh
cd tools/gateway
PORT=8787 GATEWAY_DOMAIN=gw.example.org SPA_FALLBACK=0 node server.js
# then terminate TLS in front, e.g. Caddy:  gw.example.org, *.gw.example.org { reverse_proxy 127.0.0.1:8787 }
```

Add a CDN in front if you expect marketplace traffic. Responses are cacheable by URL, and the `ETag` is the SHA-256.

## Tests

```sh
node --test test/unit.test.mjs             # offline: names, labels, paths, contentType, ABI, headers, routing,
                                           # plus end-to-end against a fake chain (agreement, 502 on disagreement,
                                           # tampered bytes, no-hash, store-changed, unpaid, blocked, lock, 304, HEAD)
LIVE=1 node --test test/live.test.mjs      # read-only mainnet: X Layer 1.2.282.tape/index.html with SHA-256 check,
                                           # Node server over HTTP, BSC/Base pinning, BSC vector 4246.0.tape
```

Selectors in `core.js` were computed with `cast sig "<signature>"` (Foundry).

## Trust model

**The gateway is untrusted.** It runs on someone's server and could serve anything. It does check the chain itself, using two or more node operators at one pinned block, implementation pinning and SHA-256, so an honest operator cannot be fooled by a single bad node. But a client cannot tell whether the operator is honest. Therefore:

- Clients that care, such as wallets, indexers and the TAP draft A tools, **MUST** verify the bytes against the hashes in the token metadata (`tap.image.sha256`, `tap.netlist.sha256`, `tap.manifest.sha256`, draft A §4.2/§7) and treat `x-tape-*` headers as hints only.
- Marketplaces that just display the bytes are trusting the gateway operator and their DNS/TLS. That is why draft A §4.2 also asks for a content-addressed copy (`ipfs://`/`ar://`) in every `uris` list.
- What remains on chain is the following. `SiteRegistry` and `DomainBinding` are UUPS proxies owned by one EOA, and the container beacon is owned by a 3/5 multisig. Implementation pinning makes a lasting upgrade fail closed (`store-changed`), but it cannot detect an upgrade that rewrites storage and restores the implementation within one transaction (TAP-10 §13.8 / Security Considerations).
- The agreement rules cannot detect every configured operator lying together, or every operator being behind at once.
- The "frozen" check trusts that a contract answering `locked()`/`processor()`/`circuitId()`/`container()` correctly really cannot write. A look-alike contract could claim to be a lock and get the one-year cache header. The bytes would still be verified at serve time, but CDNs and marketplaces could keep stale bytes for up to a year after an update.

## baseURI for TapeCode-Test1

TapeCode-Test1 builds `tokenURI = baseURI + decimal id`, with no suffix. Store the metadata in a new content circuit's container at the exact paths `meta/1` … `meta/10000`, each with `contentType` `application/json` and its SHA-256. Suppose that circuit is `#<ID>` of X Layer processor `<PROC>`, so its on-chain name is `<ID>.2.<PROC>.tape`. Then call `setBaseURI` with one of these (the trailing slash is required):

```
path form:        https://<gateway domain>/<ID>.2.<PROC>.tape/meta/
host label form:  https://<ID>-2-<PROC>.<gateway domain>/meta/
```

For example, with circuit #7 of processor 282 and a gateway at `gw.example.org`, token 1 resolves to `https://gw.example.org/7.2.282.tape/meta/1`. Point `image` inside each JSON at the same gateway, for example `https://gw.example.org/7.2.282.tape/img/1.png`, and list the `tape://7.2.282.tape/img/1.png` and `ipfs://…` URIs next to it in `tap.image.uris`. Before calling `freezeBaseURI()`, make sure that:

- the gateway domain is one you will keep running;
- `SPA_FALLBACK=0` is set;
- the container is activated far ahead (it is renewable by anyone after a `TapContainerLock`).

## Existing server-side gateway: hashport (probed 2026-10-18, read-only)

- `cname.hashport.org` resolves through 1.1.1.1, 8.8.8.8 and Cloudflare DoH to Cloudflare addresses (104.26.6.89, 104.26.7.89, 172.67.73.216). The 198.18.x.x answer from the local resolver is a fake-IP proxy artefact.
- `https://cname.hashport.org/` answers HTTP 404 with the text "This domain is not connected to a TapeOut site (needs a paid binding on BNB Chain and a _tapeout TXT record)". So a server-side gateway exists, but by its own message it serves domains bound on **BNB Chain**. Nothing found says it supports X Layer containers such as `<ID>.2.<PROC>.tape`.
- No public documentation turned up in web search. `https://hashport.org` and `https://www.hashport.org` failed the TLS handshake from this network.
- Nobody has checked whether it verifies SHA-256, uses several node operators, or what headers, CORS and caching it sends. A test would need a domain with a `_tapeout` TXT record and a paid binding.
