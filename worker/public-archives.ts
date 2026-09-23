import { archives, assetPrefix } from '../services/automation/public-archive-policy.json';

type AssetBinding = { fetch(request: Request): Promise<Response> };

function acceptsGzip(value: string | null): boolean {
  const codings = (value ?? '').toLowerCase().split(',').map(part => {
    const [name, ...parameters] = part.trim().split(';');
    const q = parameters.map(p => p.trim()).find(p => p.startsWith('q='));
    return { name, quality: q ? Number(q.slice(2)) : 1 };
  });
  const coding = codings.find(c => c.name === 'gzip') ?? codings.find(c => c.name === '*');
  return !!coding && coding.quality > 0 && coding.quality <= 1;
}

export async function servePublicArchive(request: Request, assets: AssetBinding): Promise<Response | null> {
  const url = new URL(request.url);
  const name = url.pathname.slice(1);
  if (!archives.includes(name)) return null;
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } });
  }
  url.pathname = `${assetPrefix}${name}.gz`;
  // Fetch the whole representation; never forward caller ranges or conditional tags.
  const archive = await assets.fetch(new Request(url, { headers: { 'Accept-Encoding': 'identity' } }));
  if (archive.status === 404) {
    // vinext development serves original public files without the packaging step.
    const original = await assets.fetch(new Request(request.url, { method: request.method }));
    if (original.ok && original.headers.get('Content-Type')?.includes('application/json')) return original;
    return new Response('Archive unavailable', { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }
  if (!archive.ok || !archive.body) return new Response('Archive unavailable', { status: 503, headers: { 'Cache-Control': 'no-store' } });
  const gzip = acceptsGzip(request.headers.get('Accept-Encoding'));
  const headers = new Headers({
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-cache',
    'Vary': 'Accept-Encoding',
    'X-Content-Type-Options': 'nosniff',
  });
  if (gzip) headers.set('Content-Encoding', 'gzip');
  if (request.method === 'HEAD') {
    await archive.body.cancel();
    return new Response(null, { headers });
  }
  const body = gzip ? archive.body : archive.body.pipeThrough(new DecompressionStream('gzip'));
  // Cloudflare must not gzip an already compressed body a second time.
  const init: ResponseInit & { encodeBody: 'manual' } = { headers, encodeBody: 'manual' };
  return new Response(body, init);
}
