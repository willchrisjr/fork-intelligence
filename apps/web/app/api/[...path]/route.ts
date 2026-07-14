import type { NextRequest } from "next/server";

const upstreamBase = (
  process.env.API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const upstream = new URL(
    `/api/${path.map(encodeURIComponent).join("/")}`,
    upstreamBase,
  );
  upstream.search = request.nextUrl.search;
  const headers = new Headers();
  for (const name of [
    "accept",
    "content-type",
    "last-event-id",
    "idempotency-key",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const response = await fetch(upstream, {
    method: request.method,
    headers,
    body:
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await request.arrayBuffer(),
    cache: "no-store",
    signal: request.signal,
  });
  const outgoing = new Headers(response.headers);
  outgoing.delete("content-encoding");
  outgoing.delete("content-length");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outgoing,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
