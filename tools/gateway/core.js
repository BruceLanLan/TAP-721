// TAP-10 server-side HTTPS gateway: shared core (no dependencies).
// Runs unchanged on Cloudflare Workers and Node 20+ (needs global fetch, crypto.subtle, TextEncoder).
// It resolves a TapeOut on-chain name, checks pinned implementations, activation and blocklist, reads a
// file from the site store at one pinned block agreed by >= 2 node operators, verifies size + SHA-256,
// and returns {status, headers, body}. It never sends transactions.
// SPDX-License-Identifier: MIT

// ---------------------------------------------------------------------------------------------------------
// Chain table (TAP-10 §2.1) and Deployments. Hard-coded on purpose: never learned from a server (§2.2, §5.1).
// ---------------------------------------------------------------------------------------------------------

const L2 = {
  factory: '0x1f09DAeFA827f02CBb40967cc91b259763760761',
  opener: '0x536adD8F30f03b69f6fbF29d425A816A0dC50106',
  sites: ['0xd6EFb7adCc9c83dC4924Ad56f6a8E4e969b9ADB6'],
  sitesImpl: ['0xa85c4143d1D4A77f54b8e4ecC9E6D1418Afea45f'],
  binding: '0x68809Fd2fb343aA57D0aeB7f33Defe477c9666f9',
  bindingImpl: ['0x5eBF29b80789e548907C707530C3C7607C4347Df'],
};

export const CHAINS = {
  bnb: {
    key: 'bnb', chainId: 56, area: null, maxPinLag: 400,
    factory: '0x68224F668083c29e9800Be2a646d42d18cedF7e2',
    opener: '0x021745DE2f42A7839d96f2d3634d0294487D81F1',
    sites: ['0xd006ffdd5Ae313B17729621A00999cD3C71CE5e6'],
    sitesImpl: ['0x1d279D138A4D803378a7d4557c056f1beD53c261'],
    binding: '0x861EE183de2BBE4a6ecf9D15812C123b566a3DB7',
    bindingImpl: ['0xaa226181a6588d3f9AC0035e5f3dBaF311039bCE', '0x4E8684EaEA48b524245B2191DeE451eAa1c1cA94'],
    nodes: [
      { operator: 'bnbchain', url: 'https://bsc-dataseed.bnbchain.org' },
      { operator: 'publicnode', url: 'https://bsc-rpc.publicnode.com' },
    ],
  },
  base: {
    key: 'base', chainId: 8453, area: 3, maxPinLag: 150, ...L2,
    nodes: [
      { operator: 'coinbase', url: 'https://mainnet.base.org' },
      { operator: 'publicnode', url: 'https://base-rpc.publicnode.com' },
    ],
  },
  xlayer: {
    key: 'xlayer', chainId: 196, area: 2, maxPinLag: 300, ...L2,
    nodes: [
      // The first two are both published by the X Layer / OKX side; their independence is NOT verified.
      { operator: 'xlayer', url: 'https://rpc.xlayer.tech' },
      { operator: 'okx', url: 'https://xlayerrpc.okx.com' },
      { operator: 'drpc', url: 'https://xlayer.drpc.org' },
    ],
  },
};
const AREA_TO_CHAIN = { 3: 'base', 2: 'xlayer' };

export const ERC1967_SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc';
export const MAX_FILE = 8_400_000;      // §7.1.2
export const SEGMENT = 98_304;          // §7.1.3
export const MAX_BATCH = 8;             // rpc.xlayer.tech rejects batches over ~10 calls

// Selectors (first 4 bytes of keccak256(signature)); recomputed with `cast sig` (see README).
export const SEL = {
  cpuCount: '0xa94da8a7', cpuAt: '0x4bc7cbbd', isCPU: '0x5f5a364f',
  accountOf: '0x0c1905e5', isOpened: '0x8b508494', ownerOf: '0x6352211e',
  fileInfo: '0x6c609107', read: '0xccaa7afb', readRange: '0x15a4cae2', fallbackPath: '0xa76c7713',
  operatorOf: '0x636f35d3',
  isLive: '0xd6b062cd', isContainerLive: '0xdcca979e', containerPaidUntil: '0x9ebfd859',
  locked: '0xcf309012', processor: '0xce1b1d43', circuitId: '0x030c9d5c', container: '0x90e534a7',
};

// ---------------------------------------------------------------------------------------------------------
// Names (§3.1, §3.3)
// ---------------------------------------------------------------------------------------------------------

const NUM = '(0|[1-9][0-9]*)';
const ID = '([1-9][0-9]*)';
const NAME_RE = new RegExp(`^${ID}\\.(?:${ID}\\.)?${NUM}(?:\\.tape)?$`);
const LABEL_RE = /^([1-9][0-9]*)-(?:([1-9][0-9]*)-)?(0|[1-9][0-9]*)$/;

function buildName(id, area, proc) {
  const idN = BigInt(id), procN = BigInt(proc);
  if (idN < 1n || idN > 10n ** 18n || procN > 10n ** 9n) return null;
  let chain = 'bnb';
  if (area != null) {
    chain = AREA_TO_CHAIN[area];
    if (!chain) return null; // unknown area code (incl. 0 and 1) is an input error
  }
  const name = area != null ? `${id}.${area}.${proc}.tape` : `${id}.${proc}.tape`;
  return { chain, id: idN, area: area != null ? Number(area) : null, proc: procN, name };
}

/** Parse an on-chain name or short name ("1.2.282.tape", "1.2.282", "4246.0"). Case-insensitive suffix. */
export function parseName(s) {
  if (typeof s !== 'string') return null;
  const m = NAME_RE.exec(s.toLowerCase());
  return m ? buildName(m[1], m[2], m[3]) : null;
}

/** Parse a gateway host label ("1-2-282", "4246-0"), §3.3. */
export function parseLabel(label) {
  const m = LABEL_RE.exec(String(label).toLowerCase());
  return m ? buildName(m[1], m[2], m[3]) : null;
}

export function hostLabel(n) {
  return n.area != null ? `${n.id}-${n.area}-${n.proc}` : `${n.id}-${n.proc}`;
}

// ---------------------------------------------------------------------------------------------------------
// Paths (§7.2) and content types (§7.1.6)
// ---------------------------------------------------------------------------------------------------------

/** Normalise a request path per §7.2 steps 1-3. Returns the store path or null if invalid. */
export function normalizePath(raw) {
  let p = String(raw);
  const cut = p.search(/[?#]/);
  if (cut >= 0) p = p.slice(0, cut);
  try { p = decodeURIComponent(p); } catch { return null; }
  p = p.normalize('NFC').replace(/\/{2,}/g, '/');
  if (/[\u0000-\u001f\u007f]/.test(p)) return null;
  if (p.split('/').some((seg) => seg === '.' || seg === '..')) return null;
  if (p === '' || p.endsWith('/')) p += 'index.html';
  if (p.startsWith('/')) p = p.slice(1);
  return p;
}

/** Candidate store paths in landing order (§7.2 step 4a, 4b). 4c (fallback) is added by the caller. */
export function candidatePaths(path) {
  const last = path.slice(path.lastIndexOf('/') + 1);
  const out = [path];
  if (!last.includes('.')) out.push(`${path}/index.html`);
  return out;
}

export function hasExtension(path) {
  return path.slice(path.lastIndexOf('/') + 1).includes('.');
}

export function sanitizeContentType(ct) {
  const s = String(ct ?? '').replace(/[^A-Za-z0-9_.+/;= -]/g, '').slice(0, 100);
  // §7.1.6 only requires the result to START with type/subtype.
  return /^[A-Za-z0-9][A-Za-z0-9_.+-]*\/[A-Za-z0-9][A-Za-z0-9_.+-]*/.test(s) ? s : 'application/octet-stream';
}

// ---------------------------------------------------------------------------------------------------------
// Blocklist (§10): one container address or on-chain name per line, '#' comments.
// ---------------------------------------------------------------------------------------------------------

export function parseBlocklist(text) {
  const set = new Set();
  for (const line of String(text || '').split(/\r?\n/)) {
    const t = line.trim().toLowerCase();
    if (!t || t.startsWith('#')) continue;
    const n = parseName(t);
    set.add(n ? n.name : t);
  }
  return set;
}

// ---------------------------------------------------------------------------------------------------------
// Minimal ABI
// ---------------------------------------------------------------------------------------------------------

const enc = new TextEncoder();
const hex2 = (b) => Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
const pad = (h) => h.padStart(64, '0');

export function bytesToHex(b) { return '0x' + hex2(b); }
export function hexToBytes(h) {
  const s = h.startsWith('0x') ? h.slice(2) : h;
  if (s.length % 2 || /[^0-9a-fA-F]/.test(s)) throw new Error('bad hex');
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
}

/** Encode calldata. args: [['address', a] | ['uint', n] | ['string', s]]. */
export function encodeCall(sel, args = []) {
  const heads = [], tails = [];
  let tailLen = args.length * 32;
  for (const [t, v] of args) {
    if (t === 'address') heads.push(pad(v.toLowerCase().replace(/^0x/, '')));
    else if (t === 'uint') heads.push(pad(BigInt(v).toString(16)));
    else if (t === 'string') {
      const b = enc.encode(v);
      heads.push(pad(tailLen.toString(16)));
      const body = pad(b.length.toString(16)) + hex2(b).padEnd(Math.ceil(b.length / 32) * 64, '0');
      tails.push(body);
      tailLen += body.length / 2;
    } else throw new Error('type ' + t);
  }
  return sel + heads.join('') + tails.join('');
}

export function word(h, i) {
  const s = h.replace(/^0x/, '');
  const w = s.slice(i * 64, i * 64 + 64);
  if (w.length !== 64) throw new Error('short return');
  return BigInt('0x' + w);
}
export function decAddress(h, i = 0) {
  const w = word(h, i);
  if (w >> 160n) throw new Error('non-canonical address');
  return '0x' + w.toString(16).padStart(40, '0');
}
export function decBool(h, i = 0) {
  const w = word(h, i);
  if (w > 1n) throw new Error('non-canonical bool');
  return w === 1n;
}
/** Dynamic bytes whose offset word is at index i. */
export function decBytes(h, i = 0) {
  const s = h.replace(/^0x/, '');
  const off = Number(word(h, i));
  const len = Number(BigInt('0x' + s.slice(off * 2, off * 2 + 64)));
  const start = off * 2 + 64;
  if (s.length < start + len * 2) throw new Error('short bytes');
  return hexToBytes(s.slice(start, start + len * 2));
}
export function decString(h, i = 0) { return new TextDecoder().decode(decBytes(h, i)); }

// ---------------------------------------------------------------------------------------------------------
// Nodes, agreement and the pinned block (§5)
// ---------------------------------------------------------------------------------------------------------

export class GatewayError extends Error {
  constructor(code, http, detail) { super(code); this.code = code; this.http = http; this.detail = detail; }
}

/** Normalise one JSON-RPC response object into an "answer" or undefined (not an answer), §1 and §5.2. */
export function normalizeAnswer(r) {
  if (!r || typeof r !== 'object') return undefined;
  if ('result' in r) return r.result === null ? 'null' : typeof r.result === 'string' ? r.result.toLowerCase() : undefined;
  const e = r.error;
  // An execution revert is an answer. Nodes differ on whether they include revert data, so it is dropped.
  if (e && (e.code === 3 || /revert/i.test(String(e.message)))) return 'revert';
  return undefined;
}

async function postBatch(fetchImpl, url, calls, timeoutMs) {
  const body = calls.map((c, i) => ({ jsonrpc: '2.0', id: i, method: c[0], params: c[1] }));
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetchImpl(url, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal,
    });
    if (!res.ok) throw new Error('http ' + res.status);
    const json = await res.json();
    if (!Array.isArray(json)) throw new Error('not a batch reply');
    const out = new Array(calls.length).fill(undefined);
    for (const r of json) if (Number.isInteger(r?.id) && r.id >= 0 && r.id < calls.length) out[r.id] = normalizeAnswer(r);
    return out;
  } finally { clearTimeout(t); }
}

/** Group nodes by operator label. */
function operators(nodes) {
  const m = new Map();
  for (const n of nodes) { if (!m.has(n.operator)) m.set(n.operator, []); m.get(n.operator).push(n.url); }
  return [...m.entries()].map(([operator, urls]) => ({ operator, urls }));
}

export class ChainClient {
  constructor(chain, { nodes, fetchImpl = globalThis.fetch, timeoutMs = 8000 } = {}) {
    this.chain = chain;
    this.ops = operators(nodes || chain.nodes);
    this.fetch = fetchImpl;
    this.timeoutMs = timeoutMs;
    this.chainChecked = false;
  }

  /** Send calls (chunked) to one operator, trying its nodes in order. Returns answers or null. */
  async askOperator(op, calls) {
    for (const url of op.urls) {
      try {
        const out = [];
        for (let i = 0; i < calls.length; i += MAX_BATCH) out.push(...await postBatch(this.fetch, url, calls.slice(i, i + MAX_BATCH), this.timeoutMs));
        if (out.every((a) => a !== undefined)) return out;
      } catch { /* try next node of this operator */ }
    }
    return null;
  }

  /** Default agreement (§5.2): every received answer must agree, from >= 2 operators (1 if only 1 configured). */
  async agree(calls) {
    const res = await Promise.all(this.ops.map((op) => this.askOperator(op, calls)));
    const got = res.map((r, i) => ({ r, op: this.ops[i].operator })).filter((x) => x.r);
    const need = Math.min(2, this.ops.length);
    if (got.length < need) throw new GatewayError('unavailable', 503, `answers from ${got.length} operator(s), need ${need}`);
    for (let k = 0; k < calls.length; k++) {
      const v = got[0].r[k];
      for (const g of got) if (g.r[k] !== v) throw new GatewayError('node-disagreement', 502, `${calls[k][0]} differs between ${got[0].op} and ${g.op}`);
    }
    return got[0].r;
  }

  /** Pinned block (§5.3) plus the chain check (§5.4). */
  async pin() {
    const res = await Promise.all(this.ops.map(async (op) => {
      let low = null, chainOk = true, any = false;
      await Promise.all(op.urls.map(async (url) => {
        try {
          const [cid, head] = await postBatch(this.fetch, url, [['eth_chainId', []], ['eth_blockNumber', []]], this.timeoutMs);
          if (cid === undefined || head === undefined || head === 'revert') return;
          if (BigInt(cid) !== BigInt(this.chain.chainId)) chainOk = false;
          const h = BigInt(head);
          any = true;
          if (low === null || h < low) low = h;
        } catch { /* not an answer */ }
      }));
      return { op: op.operator, head: any ? low : null, chainOk };
    }));
    if (res.some((r) => !r.chainOk)) throw new GatewayError('wrong-chain', 502, 'a node reports another chain id');
    const heads = res.filter((r) => r.head !== null).map((r) => r.head).sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
    const q = Math.min(2, this.ops.length);
    if (heads.length < q) throw new GatewayError('unavailable', 503, 'not enough operators reported a head');
    const pinned = heads[q - 1] - 2n;
    const lag = heads[0] - pinned;
    if (lag > BigInt(this.chain.maxPinLag)) throw new GatewayError('stale-block', 503, `pin lag ${lag} > ${this.chain.maxPinLag}`);
    return pinned;
  }
}

const call = (to, data, tag) => ['eth_call', [{ to, data }, tag]];
const isRevert = (a) => a === 'revert';
const isPlainCode = (code) => code === '0x' || (code.length === 2 + 46 && code.startsWith('0xef0100'));

// ---------------------------------------------------------------------------------------------------------
// Resolution (§4.2, §6) and lock detection
// ---------------------------------------------------------------------------------------------------------

/**
 * Resolve a parsed name at a fresh pinned block. Returns a resolution record with a TAP-10 status.
 * Throws GatewayError only for transport-level outcomes (unavailable, node-disagreement, stale-block, wrong-chain).
 */
export async function resolveName(client, n, { blocklist = new Set() } = {}) {
  const c = client.chain;
  const block = await client.pin();
  const tag = '0x' + block.toString(16);
  const r = { name: n.name, chainId: c.chainId, block: block.toString(), status: null };

  // Stage 1: implementations (§6.1) + processor lookup (§4.2 steps 1-2).
  const s1 = await client.agree([
    ...c.sites.map((a) => ['eth_getStorageAt', [a, ERC1967_SLOT, tag]]),
    ['eth_getStorageAt', [c.binding, ERC1967_SLOT, tag]],
    call(c.factory, SEL.cpuCount, tag),
    call(c.factory, encodeCall(SEL.cpuAt, [['uint', n.proc]]), tag),
  ]);
  const slotAddr = (w) => (w && w !== 'revert' && w !== 'null' ? decAddress(w) : null);
  const accepted = (impl, list) => impl && list.some((x) => x.toLowerCase() === impl);
  const siteImpls = c.sites.map((_, i) => slotAddr(s1[i]));
  const bindImpl = slotAddr(s1[c.sites.length]);
  r.implementations = { siteStore: siteImpls, domainBinding: bindImpl };
  if (!siteImpls.every((x) => accepted(x, c.sitesImpl)) || !accepted(bindImpl, c.bindingImpl)) return { ...r, status: 'store-changed' };

  const [cpuCountA, cpuAtA] = s1.slice(c.sites.length + 1);
  if (isRevert(cpuCountA) || BigInt(cpuCountA) <= n.proc || isRevert(cpuAtA)) return { ...r, status: 'no-such-cpu' };
  const proc = decAddress(cpuAtA);
  r.processor = proc;

  // Stage 2: container, holder, opened (§4.2 steps 3-5) + isCPU sanity.
  const s2 = await client.agree([
    call(c.opener, encodeCall(SEL.accountOf, [['address', proc], ['uint', n.id]]), tag),
    call(proc, encodeCall(SEL.ownerOf, [['uint', n.id]]), tag),
    call(c.opener, encodeCall(SEL.isOpened, [['address', proc], ['uint', n.id]]), tag),
    call(c.factory, encodeCall(SEL.isCPU, [['address', proc]]), tag),
  ]);
  if (isRevert(s2[3]) || !decBool(s2[3])) return { ...r, status: 'not-tapeout' };
  if (isRevert(s2[0])) return { ...r, status: 'not-tapeout' };
  const container = decAddress(s2[0]);
  r.container = container;
  if (isRevert(s2[1])) return { ...r, status: 'no-such-token' };
  const holder = decAddress(s2[1]);
  r.holder = holder;
  r.opened = !isRevert(s2[2]) && decBool(s2[2]);
  if (!r.opened) return { ...r, status: 'not-opened' };
  if (blocklist.has(container.toLowerCase()) || blocklist.has(n.name)) return { ...r, status: 'blocked' };

  // Stage 3: activation (§6.3), fallback path, lock inputs.
  const site = c.sites[0];
  const s3 = await client.agree([
    call(c.binding, encodeCall(SEL.isLive, [['string', n.name], ['address', container]]), tag),
    call(c.binding, encodeCall(SEL.isContainerLive, [['address', container]]), tag),
    call(c.binding, encodeCall(SEL.containerPaidUntil, [['address', container]]), tag),
    call(site, encodeCall(SEL.fallbackPath, [['address', container]]), tag),
    call(site, encodeCall(SEL.operatorOf, [['address', container]]), tag),
    ['eth_getCode', [holder, tag]],
  ]);
  const live = (!isRevert(s3[0]) && decBool(s3[0])) || (!isRevert(s3[1]) && decBool(s3[1]));
  r.activation = { live, containerPaidUntil: isRevert(s3[2]) ? null : Number(word(s3[2], 0)) };
  r.fallbackPath = isRevert(s3[3]) ? '' : decString(s3[3]);
  r.site = site;

  // Lock: writes are frozen when (a) the holder is the container itself (self-owned) or (b) the holder is a
  // TapContainerLock for exactly this circuit whose locked() is true; in both cases no site operator may be set.
  let operator = null;
  try { operator = isRevert(s3[4]) ? null : decAddress(s3[4]); } catch { operator = null; }
  const noOperator = operator === '0x0000000000000000000000000000000000000000';
  let lock = 'none';
  if (holder.toLowerCase() === container.toLowerCase()) lock = 'self-owned';
  else if (!isPlainCode(s3[5])) {
    const s4 = await client.agree([
      call(holder, SEL.locked, tag), call(holder, SEL.processor, tag),
      call(holder, SEL.circuitId, tag), call(holder, SEL.container, tag),
    ]);
    try {
      if (!s4.some(isRevert) && decBool(s4[0]) && decAddress(s4[1]) === proc.toLowerCase() &&
          word(s4[2], 0) === n.id && decAddress(s4[3]) === container.toLowerCase()) lock = 'lock-contract';
    } catch { /* not a lock */ }
  }
  r.lock = { kind: lock, operator, frozen: lock !== 'none' && noOperator };
  r.status = live ? 'ok' : 'unpaid';
  return r;
}

// ---------------------------------------------------------------------------------------------------------
// Files (§7.1)
// ---------------------------------------------------------------------------------------------------------

export async function sha256Hex(bytes) {
  return '0x' + hex2(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));
}

async function fileInfo(client, res, path) {
  const tag = '0x' + BigInt(res.block).toString(16);
  const [a] = await client.agree([call(res.site, encodeCall(SEL.fileInfo, [['address', res.container], ['string', path]]), tag)]);
  if (isRevert(a)) return null;
  const info = { path, size: Number(word(a, 0)), contentType: decString(a, 1), sha256: '0x' + word(a, 2).toString(16).padStart(64, '0'), updatedAt: Number(word(a, 3)), chunkCount: word(a, 4) };
  return info.chunkCount === 0n ? null : info;
}

/** Find the file for a normalised path using the landing order of §7.2 step 4. */
export async function locateFile(client, res, path, { spaFallback = true } = {}) {
  for (const p of candidatePaths(path)) {
    const info = await fileInfo(client, res, p);
    if (info) return info;
  }
  if (spaFallback && !hasExtension(path) && res.fallbackPath) return fileInfo(client, res, res.fallbackPath);
  return null;
}

/** Read and verify a file's bytes. Returns {bytes, verified} or throws GatewayError. */
export async function readFile(client, res, info, cache) {
  const ZERO = '0x' + '0'.repeat(64);
  if (info.sha256 === ZERO) throw new GatewayError('no-hash', 502, 'the owner declared no SHA-256; this gateway serves verified files only');
  if (info.size > MAX_FILE) throw new GatewayError('too-large', 413);
  const cached = cache?.get(info.sha256);
  if (cached && cached.length === info.size && (await sha256Hex(cached)) === info.sha256) return cached; // §11: re-verify
  const tag = '0x' + BigInt(res.block).toString(16);
  const a = ['address', res.container], p = ['string', info.path];
  const calls = info.size <= SEGMENT
    ? [call(res.site, encodeCall(SEL.read, [a, p]), tag)]
    : Array.from({ length: Math.ceil(info.size / SEGMENT) }, (_, i) => call(res.site, encodeCall(SEL.readRange, [a, p, ['uint', i * SEGMENT], ['uint', SEGMENT]]), tag));
  const answers = await client.agree(calls);
  if (answers.some(isRevert)) throw new GatewayError('incomplete', 502, 'read reverted');
  const parts = answers.map((x) => decBytes(x, 0));
  const bytes = new Uint8Array(parts.reduce((s, x) => s + x.length, 0));
  let o = 0; for (const x of parts) { bytes.set(x, o); o += x.length; }
  if (bytes.length !== info.size || (await sha256Hex(bytes)) !== info.sha256) throw new GatewayError('incomplete', 502, 'size or SHA-256 mismatch');
  cache?.set(info.sha256, bytes);
  return bytes;
}

// ---------------------------------------------------------------------------------------------------------
// Headers
// ---------------------------------------------------------------------------------------------------------

const STATUS_HTTP = { ok: 200, unpaid: 403, 'not-opened': 403, blocked: 451, 'no-such-cpu': 404, 'no-such-token': 404, 'not-tapeout': 404, 'store-changed': 502 };
export const LONG_CACHE = 'public, max-age=31536000, immutable';
export const SHORT_CACHE = 'public, max-age=60';

export function baseHeaders() {
  return {
    'access-control-allow-origin': '*',
    'access-control-expose-headers': 'etag, x-tape-name, x-tape-status, x-tape-container, x-tape-block, x-tape-sha256, x-tape-verified',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    'cross-origin-resource-policy': 'cross-origin',
  };
}

/** Headers for a verified file response (§8.8 + caching keyed by SHA-256). */
export function fileHeaders(res, info) {
  const ct = sanitizeContentType(info.contentType);
  const h = {
    ...baseHeaders(),
    'content-type': ct,
    'content-length': String(info.size),
    etag: `"${info.sha256}"`,
    'cache-control': res.lock?.frozen ? LONG_CACHE : SHORT_CACHE,
    'x-tape-name': res.name,
    'x-tape-status': res.status,
    'x-tape-container': res.container,
    'x-tape-block': res.block,
    'x-tape-sha256': info.sha256,
    'x-tape-verified': 'true',
  };
  // Files opened as documents are locked (§8.8): no script, no subresources, opaque origin. Harmless for
  // JSON and images fetched by servers or <img>, so it is applied to every file, not only text/html.
  h['content-security-policy'] = "default-src 'none'; sandbox";
  return h;
}

function plain(status, text, extra = {}) {
  return {
    status,
    headers: { ...baseHeaders(), 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', 'content-security-policy': "default-src 'none'; frame-ancestors 'none'; sandbox", ...extra },
    body: enc.encode(text + '\n'),
  };
}

function json(status, obj, extra = {}) {
  return {
    status,
    headers: { ...baseHeaders(), 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'content-security-policy': "default-src 'none'; frame-ancestors 'none'; sandbox", ...extra },
    body: enc.encode(JSON.stringify(obj, (_, v) => (typeof v === 'bigint' ? v.toString() : v), 2) + '\n'),
  };
}

// ---------------------------------------------------------------------------------------------------------
// Request routing
// ---------------------------------------------------------------------------------------------------------

/**
 * Split a request into {name, path, kind}. Host form: first label matches §3.3 and the rest equals the
 * gateway domain. Path form: /<name>/<path> on any other host. Status: /.tape/status[/<name>].
 */
export function route(host, pathname, gatewayDomain) {
  host = String(host || '').toLowerCase().replace(/:\d+$/, '');
  const dom = String(gatewayDomain || '').toLowerCase();
  if (dom && host.endsWith('.' + dom)) {
    const label = host.slice(0, -dom.length - 1);
    if (!label.includes('.')) {
      const n = parseLabel(label);
      if (!n) return { kind: 'error', code: 'input-error' };
      if (pathname === '/.tape/status' || pathname === '/.tape/status/') return { kind: 'status', name: n };
      if (pathname === '/sw.js' || pathname.startsWith('/.tape/')) return { kind: 'error', code: 'reserved' };
      return { kind: 'file', name: n, path: pathname };
    }
  }
  if (pathname === '/' || pathname === '') return { kind: 'home' };
  const sm = /^\/\.tape\/status\/([^/]+)\/?$/.exec(pathname);
  if (sm) { const n = parseName(sm[1]); return n ? { kind: 'status', name: n } : { kind: 'error', code: 'input-error' }; }
  const m = /^\/([^/]+)(\/.*)?$/.exec(pathname);
  const n = m && parseName(m[1]);
  if (!n) return { kind: 'error', code: 'input-error' };
  if (m[2] === undefined) return { kind: 'redirect', location: `/${n.name}/` };
  const rest = m[2];
  if (rest === '/sw.js' || rest.startsWith('/.tape/')) return { kind: 'error', code: 'reserved' };
  return { kind: 'file', name: n, path: rest };
}

class TTLCache {
  constructor(ttlMs, max = 500) { this.ttl = ttlMs; this.max = max; this.m = new Map(); }
  get(k) {
    const e = this.m.get(k); if (!e) return undefined;
    const age = Date.now() - e.t;
    if (age < 0 || age > this.ttl) { this.m.delete(k); return undefined; } // future timestamps are invalid (§11)
    return e.v;
  }
  set(k, v) { if (this.m.size >= this.max) this.m.delete(this.m.keys().next().value); this.m.set(k, { v, t: Date.now() }); }
}

class ByteCache {
  constructor(maxBytes) { this.max = maxBytes; this.size = 0; this.m = new Map(); }
  get(k) { const v = this.m.get(k); if (v) { this.m.delete(k); this.m.set(k, v); } return v; }
  set(k, v) {
    if (v.length > this.max / 4) return;
    if (this.m.has(k)) return;
    this.m.set(k, v); this.size += v.length;
    while (this.size > this.max) { const [k0, v0] = this.m.entries().next().value; this.m.delete(k0); this.size -= v0.length; }
  }
}

/**
 * Build a gateway. config: {gatewayDomain, nodes: {bnb:[{operator,url}], ...}, blocklist: text,
 * serveUnpaid: false, spaFallback: true (§7.2 step 4c; set false for metadata gateways), resolutionTtlMs: 15000, fileCacheBytes: 32 MiB, fetchImpl}.
 * Returns handle({method, host, url, headers}) -> Promise<{status, headers, body}>.
 */
export function createGateway(config = {}) {
  const clients = {};
  for (const k of Object.keys(CHAINS)) {
    clients[k] = new ChainClient(CHAINS[k], { nodes: config.nodes?.[k], fetchImpl: config.fetchImpl, timeoutMs: config.timeoutMs });
  }
  const blocklist = parseBlocklist(config.blocklist);
  const resCache = new TTLCache(Math.min(config.resolutionTtlMs ?? 15000, 60000));
  const fileCache = new ByteCache(config.fileCacheBytes ?? 32 * 1024 * 1024);

  async function resolve(n) {
    const hit = resCache.get(n.name);
    if (hit) return hit;
    const r = await resolveName(clients[n.chain], n, { blocklist });
    resCache.set(n.name, r);
    return r;
  }

  async function handle(req) {
    const method = String(req.method || 'GET').toUpperCase();
    if (method === 'OPTIONS') {
      return { status: 204, headers: { ...baseHeaders(), 'access-control-allow-methods': 'GET, HEAD, OPTIONS', 'access-control-allow-headers': 'if-none-match, range', 'access-control-max-age': '86400' }, body: new Uint8Array() };
    }
    if (method !== 'GET' && method !== 'HEAD') return plain(405, 'method-not-allowed', { allow: 'GET, HEAD, OPTIONS' });
    let out;
    try { out = await dispatch(req); } catch (e) {
      // A malformed node answer (short or non-canonical ABI word, unexpected null) is not trusted: fail closed.
      console.error('gateway error', e);
      out = plain(502, 'bad-answer');
    }
    if (method === 'HEAD') out.body = new Uint8Array();
    return out;
  }

  async function dispatch(req) {
    const url = new URL(req.url, 'http://x');
    const rt = route(req.host ?? url.host, url.pathname, config.gatewayDomain);
    if (rt.kind === 'home') return plain(200, 'TAP-10 server-side gateway. GET /<on-chain name>/<path>, e.g. /1.2.282.tape/index.html; status: /.tape/status/<on-chain name>');
    if (rt.kind === 'error') return plain(rt.code === 'reserved' ? 404 : 400, rt.code);
    if (rt.kind === 'redirect') return { status: 301, headers: { ...baseHeaders(), location: rt.location, 'cache-control': 'public, max-age=3600' }, body: new Uint8Array() };
    const n = rt.name;
    const tapeHeaders = { 'x-tape-name': n.name };
    let res;
    try { res = await resolve(n); } catch (e) {
      if (e instanceof GatewayError) {
        if (rt.kind === 'status') return json(e.http, { name: n.name, chainId: CHAINS[n.chain].chainId, status: e.code, detail: e.detail }, tapeHeaders);
        return plain(e.http, e.code, { ...tapeHeaders, 'x-tape-status': e.code });
      }
      throw e;
    }
    if (rt.kind === 'status') return json(200, { ...res, gateway: { verifiedFilesOnly: true, servesUnpaid: !!config.serveUnpaid } }, { ...tapeHeaders, 'x-tape-status': res.status });
    const h = { ...tapeHeaders, 'x-tape-status': res.status, ...(res.container ? { 'x-tape-container': res.container } : {}), 'x-tape-block': res.block };
    if (res.status !== 'ok' && !(res.status === 'unpaid' && config.serveUnpaid)) return plain(STATUS_HTTP[res.status] ?? 502, res.status, h);

    const path = normalizePath(rt.path);
    if (path === null) return plain(400, 'invalid-path', h);
    try {
      const info = await locateFile(clients[n.chain], res, path, { spaFallback: config.spaFallback !== false });
      if (!info) return plain(404, 'not-found', { ...h, 'cache-control': 'public, max-age=30' });
      const etag = `"${info.sha256}"`;
      const inm = req.headers?.['if-none-match'];
      if (inm && inm.split(',').map((s) => s.trim().replace(/^W\//, '')).includes(etag)) {
        const fh = fileHeaders(res, info); delete fh['content-length'];
        return { status: 304, headers: fh, body: new Uint8Array() };
      }
      const bytes = await readFile(clients[n.chain], res, info, fileCache);
      return { status: 200, headers: fileHeaders(res, info), body: bytes };
    } catch (e) {
      if (e instanceof GatewayError) return plain(e.http, e.code, { ...h, 'x-tape-verified': 'false' });
      throw e;
    }
  }

  return { handle, clients };
}

/** Parse "operator=url,operator=url" (or a JSON array of {operator,url}) into a node list. */
export function parseNodes(s) {
  if (!s) return undefined;
  const t = String(s).trim();
  if (t.startsWith('[')) return JSON.parse(t);
  return t.split(/[,\s]+/).filter(Boolean).map((x) => {
    const i = x.indexOf('=');
    return i > 0 && !x.slice(0, i).includes(':') ? { operator: x.slice(0, i), url: x.slice(i + 1) } : { operator: new URL(x).host, url: x };
  });
}

/** Build a gateway config from environment variables (Worker env or process.env). */
export function configFromEnv(env = {}) {
  return {
    gatewayDomain: env.GATEWAY_DOMAIN || '',
    nodes: { bnb: parseNodes(env.RPC_BNB), base: parseNodes(env.RPC_BASE), xlayer: parseNodes(env.RPC_XLAYER) },
    blocklist: env.BLOCKLIST || '',
    serveUnpaid: env.SERVE_UNPAID === '1',
    spaFallback: env.SPA_FALLBACK !== '0',
    resolutionTtlMs: env.RESOLUTION_TTL_MS ? Number(env.RESOLUTION_TTL_MS) : undefined,
  };
}
