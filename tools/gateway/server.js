#!/usr/bin/env node
// Node 20+ standalone server (node:http, no dependencies). Put it behind a TLS terminator (Caddy, nginx, a CDN).
// Usage: PORT=8787 GATEWAY_DOMAIN=gw.example.org node server.js
// SPDX-License-Identifier: MIT
import http from 'node:http';
import { createGateway, configFromEnv } from './core.js';

export function createServer(config = configFromEnv(process.env)) {
  const gw = createGateway(config);
  return http.createServer(async (req, res) => {
    try {
      const out = await gw.handle({
        method: req.method,
        host: req.headers.host,
        url: req.url,
        headers: { 'if-none-match': req.headers['if-none-match'] || '' },
      });
      res.writeHead(out.status, out.headers);
      res.end(out.status === 304 || out.status === 204 ? undefined : Buffer.from(out.body));
    } catch (e) {
      console.error(e);
      res.writeHead(500, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
      res.end('internal-error\n');
    }
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.PORT || 8787);
  createServer().listen(port, () => console.log(`tap gateway listening on :${port}`));
}
