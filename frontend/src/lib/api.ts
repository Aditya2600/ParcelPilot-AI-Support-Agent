// The FastAPI origin is baked in at build time (NEXT_PUBLIC_* vars are inlined
// into the browser bundle by Next, not read at container start). An unset value
// falls back to same-origin, which only works if something in front of the
// frontend proxies /api/* itself.
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}
