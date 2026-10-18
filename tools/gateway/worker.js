// Cloudflare Worker entry (ES module). Deploy with `wrangler deploy`; configuration in wrangler.toml [vars].
// SPDX-License-Identifier: MIT
import { createGateway, configFromEnv } from './core.js';

let gw = null;

export default {
  async fetch(request, env) {
    gw ??= createGateway(configFromEnv(env));
    const url = new URL(request.url);
    const out = await gw.handle({
      method: request.method,
      host: url.host,
      url: url.pathname + url.search,
      headers: { 'if-none-match': request.headers.get('if-none-match') || '' },
    });
    const nullBody = out.status === 204 || out.status === 304 || out.status === 301 || request.method === 'HEAD';
    return new Response(nullBody ? null : out.body, { status: out.status, headers: out.headers });
  },
};
