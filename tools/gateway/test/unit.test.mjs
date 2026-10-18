// Offline unit tests: node --test test/unit.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  parseName, parseLabel, hostLabel, normalizePath, candidatePaths, sanitizeContentType, parseBlocklist,
  encodeCall, decString, decBytes, normalizeAnswer, route, fileHeaders, createGateway, CHAINS, SEL,
  ERC1967_SLOT, LONG_CACHE, SHORT_CACHE, sha256Hex, parseNodes,
} from '../core.js';

test('names (§3.1)', () => {
  const a = parseName('1.2.282.tape');
  assert.equal(a.chain, 'xlayer'); assert.equal(a.id, 1n); assert.equal(a.proc, 282n); assert.equal(a.name, '1.2.282.tape');
  assert.equal(parseName('1.2.282').name, '1.2.282.tape');
  assert.equal(parseName('1.2.282.TAPE').name, '1.2.282.tape');
  assert.equal(parseName('4246.0').chain, 'bnb');
  assert.equal(parseName('4246.0.tape').name, '4246.0.tape');
  assert.equal(parseName('1.3.1').chain, 'base');
  for (const bad of ['04246.0', '0.0.tape', '4246', '1.0.5', '1.1.5', '1.4.5', '1.2.0282', '', 'a.b', '1..2', '1.2.3.4.tape',
    '1000000000000000001.0', '1.1000000001']) assert.equal(parseName(bad), null, bad);
  assert.ok(parseName('1000000000000000000.1000000000'));
});

test('host labels (§3.3)', () => {
  assert.equal(parseLabel('1-2-282').name, '1.2.282.tape');
  assert.equal(parseLabel('4246-0').name, '4246.0.tape');
  assert.equal(parseLabel('1-3-1').chain, 'base');
  for (const bad of ['0-0', '1-1-5', '1-0-5', '1-4-5', '01-0', '1-2-03', '1_2_3', '1-2-3-4']) assert.equal(parseLabel(bad), null, bad);
  assert.equal(hostLabel(parseName('1.2.282')), '1-2-282');
  assert.equal(hostLabel(parseName('4246.0')), '4246-0');
});

test('path rules (§7.2)', () => {
  assert.equal(normalizePath('/'), 'index.html');
  assert.equal(normalizePath(''), 'index.html');
  assert.equal(normalizePath('/docs/'), 'docs/index.html');
  assert.equal(normalizePath('/meta/1'), 'meta/1');
  assert.equal(normalizePath('//meta///1?x=1#y'), 'meta/1');
  assert.equal(normalizePath('/a%20b.txt'), 'a b.txt');
  assert.equal(normalizePath('/caf%C3%A9'), 'café');
  assert.equal(normalizePath('/café'), 'café'); // NFC
  assert.equal(normalizePath('/%zz'), null);
  assert.equal(normalizePath('/a/../b'), null);
  assert.equal(normalizePath('/a/%2e%2e/b'), null);
  assert.equal(normalizePath('/./b'), null);
  assert.equal(normalizePath('/a%00b'), null);
  assert.equal(normalizePath('/a%7f'), null);
  // exact match first; extension-less paths also try <path>/index.html
  assert.deepEqual(candidatePaths('meta/1'), ['meta/1', 'meta/1/index.html']);
  assert.deepEqual(candidatePaths('img/1.png'), ['img/1.png']);
});

test('contentType sanitising (§7.1.6)', () => {
  assert.equal(sanitizeContentType('application/json'), 'application/json');
  assert.equal(sanitizeContentType('text/html; charset=utf-8'), 'text/html; charset=utf-8');
  assert.equal(sanitizeContentType('image/svg+xml'), 'image/svg+xml');
  assert.equal(sanitizeContentType('text/html\r\nSet-Cookie: a=b'), 'text/htmlSet-Cookie a=b');
  assert.equal(/[\r\n:]/.test(sanitizeContentType('text/html\r\nSet-Cookie: a=b')), false);
  assert.equal(sanitizeContentType('json'), 'application/octet-stream');
  assert.equal(sanitizeContentType(''), 'application/octet-stream');
  assert.equal(sanitizeContentType('<script>'), 'application/octet-stream');
  assert.equal(sanitizeContentType('text/plain; x="y"'), 'text/plain; x=y');
  assert.equal(sanitizeContentType('a/' + 'b'.repeat(200)).length, 100);
});

test('blocklist (§10)', () => {
  const s = parseBlocklist('# c\n0xABCdef0000000000000000000000000000000001\n4246.0\n\n');
  assert.ok(s.has('0xabcdef0000000000000000000000000000000001'));
  assert.ok(s.has('4246.0.tape'));
});

test('ABI round trip', () => {
  const d = encodeCall(SEL.fileInfo, [['address', '0xa8Edd3B032D33aA0657a3E151a7F8c3e5F71F6B9'], ['string', 'index.html']]);
  assert.equal(d, '0x6c609107000000000000000000000000a8edd3b032d33aa0657a3e151a7f8c3e5f71f6b90000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000a696e6465782e68746d6c00000000000000000000000000000000000000000000');
  const ret = '0x' + '0'.repeat(62) + '20' + '0'.repeat(63) + 'a' + '696e6465782e68746d6c'.padEnd(64, '0');
  assert.equal(decString(ret), 'index.html');
  assert.deepEqual([...decBytes('0x' + '0'.repeat(62) + '20' + '0'.repeat(64))], []);
});

test('answer normalisation (§5.2)', () => {
  assert.equal(normalizeAnswer({ result: '0xABC' }), '0xabc');
  assert.equal(normalizeAnswer({ result: null }), 'null');
  assert.equal(normalizeAnswer({ error: { code: 3, message: 'execution reverted', data: '0x12' } }), 'revert');
  assert.equal(normalizeAnswer({ error: { code: -32000, message: 'execution reverted' } }), 'revert');
  assert.equal(normalizeAnswer({ error: { code: -32005, message: 'rate limited' } }), undefined);
  assert.equal(normalizeAnswer({}), undefined);
});

test('routing', () => {
  assert.deepEqual(route('gw.example.org', '/1.2.282.tape/meta/1', 'gw.example.org').path, '/meta/1');
  assert.equal(route('gw.example.org', '/1.2.282.tape/meta/1', 'gw.example.org').name.name, '1.2.282.tape');
  assert.equal(route('1-2-282.gw.example.org', '/meta/1', 'gw.example.org').name.name, '1.2.282.tape');
  assert.equal(route('1-2-282.gw.example.org:443', '/.tape/status', 'gw.example.org').kind, 'status');
  assert.equal(route('1-2-282.gw.example.org', '/sw.js', 'gw.example.org').code, 'reserved');
  assert.equal(route('1-2-282.gw.example.org', '/.tape/x', 'gw.example.org').code, 'reserved');
  assert.equal(route('1-1-282.gw.example.org', '/', 'gw.example.org').code, 'input-error');
  assert.equal(route('gw.example.org', '/.tape/status/1.2.282.tape', 'gw.example.org').kind, 'status');
  assert.equal(route('gw.example.org', '/1.2.282.tape', 'gw.example.org').location, '/1.2.282.tape/');
  assert.equal(route('localhost:8787', '/1.2.282/x', '').name.name, '1.2.282.tape');
  assert.equal(route('localhost', '/1.2.282.tape/.tape/status', '').code, 'reserved');
  assert.equal(route('localhost', '/hello/x', '').code, 'input-error');
});

test('headers (§8.8, caching, CSP, CORS)', () => {
  const res = { name: '1.2.282.tape', status: 'ok', container: '0xa8edd3b032d33aa0657a3e151a7f8c3e5f71f6b9', block: '123', lock: { frozen: false } };
  const info = { size: 5, contentType: 'application/json', sha256: '0x' + 'ab'.repeat(32) };
  const h = fileHeaders(res, info);
  assert.equal(h['x-tape-name'], '1.2.282.tape');
  assert.equal(h['x-tape-status'], 'ok');
  assert.equal(h['x-tape-container'], res.container);
  assert.equal(h['x-tape-block'], '123');
  assert.equal(h['x-tape-sha256'], info.sha256);
  assert.equal(h['x-tape-verified'], 'true');
  assert.equal(h.etag, `"${info.sha256}"`);
  assert.equal(h['access-control-allow-origin'], '*');
  assert.equal(h['x-content-type-options'], 'nosniff');
  assert.equal(h['cache-control'], SHORT_CACHE);
  assert.equal(h['content-type'], 'application/json');
  assert.equal(fileHeaders({ ...res, lock: { frozen: true } }, info)['cache-control'], LONG_CACHE);
  const html = fileHeaders(res, { ...info, contentType: 'text/html; charset=utf-8' });
  assert.equal(html['content-security-policy'], "default-src 'none'; sandbox");
});

test('node list parsing', () => {
  assert.deepEqual(parseNodes('a=https://x.org,b=https://y.org'), [{ operator: 'a', url: 'https://x.org' }, { operator: 'b', url: 'https://y.org' }]);
  assert.deepEqual(parseNodes('https://x.org/rpc'), [{ operator: 'x.org', url: 'https://x.org/rpc' }]);
});

// ---------------------------------------------------------------------------------------------------------
// End-to-end against a fake X Layer (no network)
// ---------------------------------------------------------------------------------------------------------

const X = CHAINS.xlayer;
const PROC = '0x8e0bb87998a9239daa79551ef7dbf78c9b0c60cf';
const CONT = '0xa8edd3b032d33aa0657a3e151a7f8c3e5f71f6b9';
const HOLDER = '0x1183a1a0f98dd2ef8f66895c6811bbf43032843e';
const LOCK = '0x00000000000000000000000000000000000010c4';
const w = (x) => BigInt(x).toString(16).padStart(64, '0');
const wa = (a) => a.slice(2).padStart(64, '0');
const dyn = (bytes) => w(bytes.length) + Buffer.from(bytes).toString('hex').padEnd(Math.ceil(bytes.length / 32) * 64, '0');
const retBytes = (b) => '0x' + w(32) + dyn(b);

function decodeStringArg(data, argIndex) {
  const s = data.slice(10);
  const off = Number(BigInt('0x' + s.slice(argIndex * 64, argIndex * 64 + 64)));
  const len = Number(BigInt('0x' + s.slice(off * 2, off * 2 + 64)));
  return Buffer.from(s.slice(off * 2 + 64, off * 2 + 64 + len * 2), 'hex').toString();
}

async function fakeChain({ files, holder = HOLDER, live = true, impl = X.sitesImpl[0], lie = null }) {
  const store = {};
  for (const [p, f] of Object.entries(files)) {
    const bytes = Buffer.from(f.body);
    store[p] = { ...f, bytes, sha: f.sha ?? (await sha256Hex(bytes)) };
  }
  function answer(method, params, url) {
    if (method === 'eth_chainId') return '0xc4';
    if (method === 'eth_blockNumber') return '0x1000';
    if (method === 'eth_getStorageAt') return '0x' + wa(params[0].toLowerCase() === X.sites[0].toLowerCase() ? impl.toLowerCase() : X.bindingImpl[0].toLowerCase());
    if (method === 'eth_getCode') return params[0].toLowerCase() === LOCK ? '0x6000' : '0x';
    const { to, data } = params[0];
    const sel = data.slice(0, 10);
    const t = to.toLowerCase();
    if (lie && url.includes(lie.node) && sel === lie.sel) return lie.value;
    if (t === X.factory.toLowerCase()) {
      if (sel === SEL.cpuCount) return '0x' + w(300);
      if (sel === SEL.cpuAt) return '0x' + wa(PROC);
      if (sel === SEL.isCPU) return '0x' + w(1);
    }
    if (t === X.opener.toLowerCase()) {
      if (sel === SEL.accountOf) return '0x' + wa(CONT);
      if (sel === SEL.isOpened) return '0x' + w(1);
    }
    if (t === PROC && sel === SEL.ownerOf) return '0x' + wa(holder);
    if (t === X.binding.toLowerCase()) {
      if (sel === SEL.isLive) return '0x' + w(live ? 1 : 0);
      if (sel === SEL.isContainerLive) return { revert: true };
      if (sel === SEL.containerPaidUntil) return '0x' + w(0);
    }
    if (t === LOCK) {
      if (sel === SEL.locked) return '0x' + w(1);
      if (sel === SEL.processor) return '0x' + wa(PROC);
      if (sel === SEL.circuitId) return '0x' + w(1);
      if (sel === SEL.container) return '0x' + wa(CONT);
    }
    if (t === X.sites[0].toLowerCase()) {
      if (sel === SEL.fallbackPath) return retBytes(Buffer.from('index.html'));
      if (sel === SEL.operatorOf) return '0x' + w(0);
      const path = decodeStringArg(data, 1);
      const f = store[path];
      if (sel === SEL.fileInfo) {
        if (!f) return '0x' + w(0) + w(160) + w(0) + w(0) + w(0) + w(0);
        return '0x' + w(f.bytes.length) + w(160) + f.sha.slice(2) + w(1) + w(1) + dyn(Buffer.from(f.ct));
      }
      if (sel === SEL.read) return f ? retBytes(f.tamper ?? f.bytes) : { revert: true };
    }
    return { revert: true };
  }
  return async (url, init) => {
    const calls = JSON.parse(init.body);
    const out = calls.map((c) => {
      const a = answer(c.method, c.params, url);
      return a && a.revert ? { jsonrpc: '2.0', id: c.id, error: { code: 3, message: 'execution reverted' } } : { jsonrpc: '2.0', id: c.id, result: a };
    });
    return new Response(JSON.stringify(out), { status: 200, headers: { 'content-type': 'application/json' } });
  };
}

const NODES = { xlayer: [{ operator: 'a', url: 'https://a.test' }, { operator: 'b', url: 'https://b.test' }] };
const META = '{"name":"TCT1 #1","image":"https://gw.example.org/1.2.282.tape/img/1.png"}';
const FILES = {
  'index.html': { body: '<h1>hi</h1>', ct: 'text/html; charset=utf-8' },
  'meta/1': { body: META, ct: 'application/json' },
  'meta/1/index.html': { body: 'wrong', ct: 'text/html' },
};

async function gw(opts = {}) {
  return createGateway({ gatewayDomain: 'gw.example.org', nodes: NODES, fetchImpl: await fakeChain({ files: FILES, ...opts }), resolutionTtlMs: 0 });
}
const get = (g, url, host = 'gw.example.org', headers = {}) => g.handle({ method: 'GET', host, url, headers });

test('e2e: meta/1 served as exact JSON file with headers', async () => {
  const g = await gw();
  const r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.status, 200);
  assert.equal(Buffer.from(r.body).toString(), META);
  assert.equal(r.headers['content-type'], 'application/json');
  assert.equal(r.headers['x-tape-verified'], 'true');
  assert.equal(r.headers['x-tape-block'], String(0x1000 - 2));
  assert.equal(r.headers['x-tape-container'], CONT);
  assert.equal(r.headers['cache-control'], SHORT_CACHE);
  const h = await get(g, '/meta/1', '1-2-282.gw.example.org');
  assert.equal(Buffer.from(h.body).toString(), META);
  const nm = await get(g, '/1.2.282.tape/meta/1', 'gw.example.org', { 'if-none-match': r.headers.etag });
  assert.equal(nm.status, 304);
});

test('e2e: SPA fallback for extension-less miss, 404 for missing file with extension', async () => {
  const g = await gw();
  const fb = await get(g, '/1.2.282.tape/some/route');
  assert.equal(fb.status, 200);
  assert.equal(fb.headers['content-type'], 'text/html; charset=utf-8');
  assert.equal(fb.headers['content-security-policy'], "default-src 'none'; sandbox");
  assert.equal((await get(g, '/1.2.282.tape/missing.png')).status, 404);
});

test('e2e: node disagreement fails closed with 502', async () => {
  const g = await gw({ lie: { node: 'b.test', sel: SEL.accountOf, value: '0x' + wa('0x000000000000000000000000000000000000dead') } });
  const r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.status, 502);
  assert.equal(Buffer.from(r.body).toString().trim(), 'node-disagreement');
  assert.equal(r.headers['cache-control'], 'no-store');
});

test('e2e: tampered bytes are not served', async () => {
  const files = { ...FILES, 'meta/1': { ...FILES['meta/1'], tamper: Buffer.from(META.replace('#1', '#2')) } };
  const g = createGateway({ nodes: NODES, fetchImpl: await fakeChain({ files }), resolutionTtlMs: 0 });
  const r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.status, 502);
  assert.equal(Buffer.from(r.body).toString().trim(), 'incomplete');
});

test('e2e: no-hash files are refused', async () => {
  const files = { 'a.json': { body: '{}', ct: 'application/json', sha: '0x' + '0'.repeat(64) } };
  const g = createGateway({ nodes: NODES, fetchImpl: await fakeChain({ files }), resolutionTtlMs: 0 });
  assert.equal(Buffer.from((await get(g, '/1.2.282.tape/a.json')).body).toString().trim(), 'no-hash');
});

test('e2e: store-changed, unpaid, blocked', async () => {
  let g = await gw({ impl: '0x0000000000000000000000000000000000000bad' });
  let r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.status, 502); assert.equal(r.headers['x-tape-status'], 'store-changed');
  g = await gw({ live: false });
  r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.status, 403); assert.equal(r.headers['x-tape-status'], 'unpaid');
  g = createGateway({ nodes: NODES, fetchImpl: await fakeChain({ files: FILES }), blocklist: '1.2.282.tape', resolutionTtlMs: 0 });
  r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.status, 451);
});

test('e2e: lock contract gives long cache; status endpoint reports it', async () => {
  const g = await gw({ holder: LOCK });
  const r = await get(g, '/1.2.282.tape/meta/1');
  assert.equal(r.headers['cache-control'], LONG_CACHE);
  const s = await get(g, '/.tape/status/1.2.282.tape');
  const j = JSON.parse(Buffer.from(s.body).toString());
  assert.equal(j.status, 'ok');
  assert.equal(j.lock.kind, 'lock-contract');
  assert.equal(j.lock.frozen, true);
  assert.equal(j.block, String(0x1000 - 2));
  assert.equal(j.container, CONT);
});

test('e2e: HEAD and OPTIONS', async () => {
  const g = await gw();
  const h = await g.handle({ method: 'HEAD', host: 'gw.example.org', url: '/1.2.282.tape/meta/1' });
  assert.equal(h.status, 200); assert.equal(h.body.length, 0); assert.equal(h.headers['content-length'], String(META.length));
  const o = await g.handle({ method: 'OPTIONS', host: 'gw.example.org', url: '/1.2.282.tape/meta/1' });
  assert.equal(o.status, 204);
  assert.equal((await g.handle({ method: 'POST', host: 'gw.example.org', url: '/' })).status, 405);
});

test('e2e: spaFallback=false turns an extension-less miss into 404', async () => {
  const g = createGateway({ nodes: NODES, fetchImpl: await fakeChain({ files: FILES }), resolutionTtlMs: 0, spaFallback: false });
  assert.equal((await get(g, '/1.2.282.tape/meta/2')).status, 404);
  assert.equal((await get(g, '/1.2.282.tape/meta/1')).status, 200);
});

test('e2e: malformed node answer fails closed with 502 bad-answer', async () => {
  const fetchImpl = await fakeChain({ files: FILES, lie: { node: '.test', sel: SEL.accountOf, value: '0x' } });
  const g = createGateway({ nodes: NODES, fetchImpl, resolutionTtlMs: 0 });
  const orig = console.error; console.error = () => {};
  try {
    const r = await get(g, '/1.2.282.tape/meta/1');
    assert.equal(r.status, 502);
    assert.equal(Buffer.from(r.body).toString().trim(), 'bad-answer');
  } finally { console.error = orig; }
});
