/**
 * Same-origin proxy to the FastAPI service.
 *
 * The browser must not call the API host directly: free tunnels (pinggy, serveo)
 * answer browser-like requests with an HTML warning page, which breaks CORS and
 * JSON parsing. Forwarding from a serverless function sends plain server headers
 * instead, so the upstream answers JSON and the SPA only talks to its own origin.
 *
 * `API_UPSTREAM` is the deployed backend origin and must be set in Vercel. There
 * is deliberately no baked-in default: pointing at a dead tunnel produced a bare
 * "fetch failed" in the UI, which hid the real problem.
 */
const UPSTREAM = (process.env.API_UPSTREAM || '').replace(/\/+$/, '');

export default async function proxy(req, res) {
  if (!UPSTREAM) {
    res.status(503).json({ detail: 'API_UPSTREAM is not configured for this deployment.' });
    return;
  }

  const target = `${UPSTREAM}${req.url.replace(/^\/api/, '')}`;
  const headers = { accept: 'application/json' };
  if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];
  // Kept so authentication can be switched back on later without touching this file.
  if (req.headers.authorization) headers.authorization = req.headers.authorization;
  // Anonymous reviewer identity (see frontend/src/services/api.ts).
  if (req.headers['x-guest-id']) headers['x-guest-id'] = req.headers['x-guest-id'];

  const init = { method: req.method, headers, redirect: 'manual' };
  if (req.method !== 'GET' && req.method !== 'HEAD' && req.body !== undefined && req.body !== null) {
    init.body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    headers['content-type'] = headers['content-type'] || 'application/json';
  }

  try {
    const upstream = await fetch(target, init);
    // Forward bytes, not a decoded string: the API answers with a bare
    // `application/json` content type, so decoding here and letting res.send()
    // re-encode it turned "→" and "·" in the agent trace into "â†’" / "Â·".
    const body = Buffer.from(await upstream.arrayBuffer());
    const type = upstream.headers.get('content-type') || 'application/json';
    const textual = /^(text\/|application\/(json|xml|javascript|x-ndjson))/i.test(type);
    res.status(upstream.status);
    res.setHeader('content-type', textual && !/charset=/i.test(type) ? `${type}; charset=utf-8` : type);
    res.setHeader('cache-control', 'no-store');
    res.send(body);
  } catch (error) {
    res.status(502).json({ detail: `API unreachable: ${error.message}` });
  }
}
