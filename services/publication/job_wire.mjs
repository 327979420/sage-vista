// Shared strict JSON byte framing only; no identity or business validation.
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function base64(bytes) {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return btoa(binary);
}

function response(value, status = 200) {
  return new Response(JSON.stringify(canonical(value)), { status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

async function body(request, limit) {
  if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json" ||
      ![null, "identity"].includes(request.headers.get("Content-Encoding"))) throw new Error("invalid");
  const length = request.headers.get("Content-Length");
  if (length !== null && (!/^[0-9]+$/.test(length) || Number(length) > limit)) throw new Error("invalid");
  if (!request.body) throw new Error("invalid");
  const reader = request.body.getReader();
  let timer;
  try {
    const read = async () => {
      const chunks = [];
      let size = 0;
      while (true) {
        const item = await reader.read();
        if (item.done) break;
        size += item.value.length;
        if (size > limit) throw new Error("invalid");
        chunks.push(item.value);
      }
      if (!size || (length !== null && size !== Number(length))) throw new Error("invalid");
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
      const value = JSON.parse(text);
      if (!value || Array.isArray(value) || typeof value !== "object" || JSON.stringify(canonical(value)) !== text) throw new Error("invalid");
      return value;
    };
    return await Promise.race([read(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("invalid")), 5000);
    })]);
  } finally {
    clearTimeout(timer);
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export { body, base64, response };
