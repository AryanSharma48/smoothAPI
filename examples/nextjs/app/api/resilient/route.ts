import { createResilientFetch } from '@codingaryan/smoothapi';

// This route makes a live request on every call, so opt out of static
// prerendering at build time.
export const dynamic = 'force-dynamic';

const SANDBOX_URL = 'http://localhost:3001/unstable-data';

// Fallback payload returned when the API can't be reached. Typing it here lets
// the result be discriminated from a real Response below.
const FALLBACK = { data: 'cached fallback (stale)' };

// Created once at module scope so the circuit-breaker state is shared across
// requests instead of being reset on every call.
const resilientFetch = createResilientFetch<typeof FALLBACK>({
  // Keep the default backoff/retry settings.
  retryOn: [429, 500, 502, 503, 504],
  fallback: FALLBACK,
  fallbackOnNonRetryable: true,
  // Server-side: log instead of the browser-alert default.
  onNonRetryableError: (status, message) => {
    console.error(`[resilient] non-retryable ${status}: ${message}`);
  },
});

export async function GET() {
  // no-store: Next.js caches fetch() by default, which would hide the
  // unstable API's varying responses. We want a live call every time.
  const result = await resilientFetch(SANDBOX_URL, { cache: 'no-store' });

  // A Response means we reached the network; the fallback object means we
  // returned the stale cached value instead.
  if (result instanceof Response) {
    const data = await result.json().catch(() => null);
    return Response.json({ source: 'live', status: result.status, data });
  }

  return Response.json({ source: 'fallback', data: result });
}
