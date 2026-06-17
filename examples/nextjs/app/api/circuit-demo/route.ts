import { createResilientFetch } from '@codingaryan/smoothapi';

// This route makes a live request on every call, so opt out of static
// prerendering at build time.
export const dynamic = 'force-dynamic';

const SANDBOX_URL = 'http://localhost:3001/always-fail';

const FALLBACK = { data: 'circuit-open fallback' };

// Module-scoped so the breaker state survives across requests. /always-fail
// never succeeds, so consecutive failures accumulate until the circuit trips.
const resilientFetch = createResilientFetch<typeof FALLBACK>({
  retryOn: [429, 500, 502, 503, 504],
  circuitBreaker: {
    failureThreshold: 3,
    cooldownMs: 5000, // short cooldown so the demo recovers quickly
  },
  fallback: FALLBACK,
  onNonRetryableError: (status, message) => {
    console.error(`[circuit-demo] non-retryable ${status}: ${message}`);
  },
});

export async function GET() {
  // no-store: bypass Next.js's default fetch cache so every call is a real
  // request — otherwise the breaker would never see repeated failures.
  const result = await resilientFetch(SANDBOX_URL, { cache: 'no-store' });

  // A Response means the request reached the network (and retried). The
  // fallback object means the OPEN circuit short-circuited before any IO.
  if (result instanceof Response) {
    return Response.json({
      hitNetwork: true,
      behavior: 'retried against the API, then returned the upstream response',
      status: result.status,
    });
  }

  return Response.json({
    hitNetwork: false,
    behavior: 'circuit OPEN — instant fallback, no network request made',
    data: result,
  });
}
