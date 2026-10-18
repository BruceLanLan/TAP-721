// Live, read-only integration test against X Layer mainnet (and BSC/Base pinning). Never sends transactions.
// Run: LIVE=1 node --test test/live.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createGateway, ChainClient, CHAINS, sha256Hex } from '../core.js';
import { createServer } from '../server.js';

const LIVE = process.env.LIVE === '1';
const XLAYER_NODES = [
  { operator: 'xlayer', url: 'https://rpc.xlayer.tech' },
  { operator: 'okx', url: 'https://xlayerrpc.okx.com' },
];

test('live: 1.2.282.tape/index.html is read at a pinned block and its SHA-256 verified', { skip: !LIVE, timeout: 60000 }, async () => {
  const g = createGateway({ nodes: { xlayer: XLAYER_NODES } });
  const st = await g.handle({ method: 'GET', host: 'localhost', url: '/.tape/status/1.2.282.tape' });
  const status = JSON.parse(Buffer.from(st.body).toString());
  console.log('status:', JSON.stringify({ status: status.status, block: status.block, container: status.container, holder: status.holder, lock: status.lock, activation: status.activation }));
  assert.equal(status.status, 'ok');
  assert.equal(status.container.toLowerCase(), '0xa8edd3b032d33aa0657a3e151a7f8c3e5f71f6b9');
  assert.equal(status.processor.toLowerCase(), '0x8e0bb87998a9239daa79551ef7dbf78c9b0c60cf');

  const r = await g.handle({ method: 'GET', host: 'localhost', url: '/1.2.282.tape/index.html' });
  assert.equal(r.status, 200, Buffer.from(r.body).toString());
  const sha = await sha256Hex(r.body);
  console.log(`index.html: ${r.body.length} bytes, sha256 ${sha}, block ${r.headers['x-tape-block']}, content-type ${r.headers['content-type']}, cache-control ${r.headers['cache-control']}`);
  // Primary check: our own hash of the served bytes equals the on-chain fileInfo hash the gateway reported.
  assert.equal(sha, r.headers['x-tape-sha256']);
  assert.equal(String(r.body.length), r.headers['content-length']);
  assert.equal(r.headers['x-tape-verified'], 'true');
  assert.equal(r.headers['content-security-policy'], "default-src 'none'; sandbox");
  // Secondary: the value observed on 2026-10-18 (the holder may update the file later).
  assert.equal(sha, '0x108677f22b768bfc77b1aa55234a74e2a14f11f3431297a4254597888aa02208', 'index.html changed since 2026-10-18 (owner update?)');

  const miss = await g.handle({ method: 'GET', host: 'localhost', url: '/1.2.282.tape/meta/1' });
  console.log('meta/1 (not uploaded yet):', miss.status, miss.headers['content-type'], miss.headers['x-tape-sha256'] === r.headers['x-tape-sha256'] ? '(SPA fallback = index.html)' : '');
});

test('live: with SPA_FALLBACK off, a missing meta/1 is a 404', { skip: !LIVE, timeout: 60000 }, async () => {
  const g = createGateway({ nodes: { xlayer: XLAYER_NODES }, spaFallback: false });
  const miss = await g.handle({ method: 'GET', host: 'localhost', url: '/1.2.282.tape/meta/1' });
  assert.equal(miss.status, 404);
});

test('live: Node server end to end over HTTP', { skip: !LIVE, timeout: 60000 }, async () => {
  const srv = createServer({ nodes: { xlayer: XLAYER_NODES } });
  await new Promise((ok) => srv.listen(0, ok));
  try {
    const port = srv.address().port;
    const res = await fetch(`http://127.0.0.1:${port}/1.2.282.tape/`);
    const body = new Uint8Array(await res.arrayBuffer());
    assert.equal(res.status, 200);
    assert.equal(await sha256Hex(body), res.headers.get('x-tape-sha256'));
    assert.equal(res.headers.get('access-control-allow-origin'), '*');
    const again = await fetch(`http://127.0.0.1:${port}/1.2.282.tape/`, { headers: { 'if-none-match': res.headers.get('etag') } });
    assert.equal(again.status, 304);
  } finally { srv.close(); }
});

test('live: pinned blocks on BSC and Base with two operators', { skip: !LIVE, timeout: 60000 }, async () => {
  for (const k of ['bnb', 'base']) {
    const b = await new ChainClient(CHAINS[k]).pin();
    console.log(`${k} pinned block ${b}`);
    assert.ok(b > 0n);
  }
});

test('live: BSC test vector 4246.0.tape resolves (status may be unpaid after its expiry)', { skip: !LIVE, timeout: 60000 }, async () => {
  const g = createGateway({});
  const st = await g.handle({ method: 'GET', host: 'localhost', url: '/.tape/status/4246.0.tape' });
  const j = JSON.parse(Buffer.from(st.body).toString());
  console.log('4246.0.tape:', j.status, j.container, j.block);
  assert.equal(j.container?.toLowerCase(), '0x86ddaef00401e3f10418398d67d7189fc458ea95');
});
