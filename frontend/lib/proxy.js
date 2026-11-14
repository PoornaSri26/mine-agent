/**
 * Same-origin proxy to the FastAPI service.
 *
 * The browser must not call the API host directly: free tunnels (pinggy, serveo)
 * answer browser-like requests with an HTML warning page, which breaks CORS and
 * JSON parsing. Forwarding from a serverless function sends plain server headers
 * instead, so the upstream answers JSON and the SPA only talks to its own origin.
 *
 * `API_UPSTREAM` overrides the target; set it in Vercel when the backend moves.
 */
const UPSTREAM = (process.env.API_UPSTREAM || 'https://hlxxy-103-54-178-18.free.pinggy.net').replace(/\/+$/, '');

export default async function proxy(req, res) {
  const target = `${UPSTREAM}${req.url.replace(/^\/api/, '')}`;
  const headers = { accept: 'application/json' };
  if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];
  if (req.headers.authorization) headers.authorization = req.headers.authorization;

  const init = { method: req.method, headers, redirect: 'manual' };
  if (req.method !== 'GET' && req.method !== 'HEAD' && req.body !== undefined && req.body !== null) {
    init.body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    headers['content-type'] = headers['content-type'] || 'application/json';
  }

  try {
    const upstream = await fetch(target, init);
    const body = await upstream.text();
    res.status(upstream.status);
    res.setHeader('content-type', upstream.headers.get('content-type') || 'application/json');
    res.setHeader('cache-control', 'no-store');
    res.send(body);
  } catch (error) {
    res.status(502).json({ detail: `API unreachable: ${error.message}` });
  }
}
