import { createSmoothFetch } from '@codingaryan/smoothapi';

export const dynamic = 'force-dynamic';

const SANDBOX_URL = 'http://localhost:3001/delayed?ms=2500';

const TIMEOUT_FALLBACK = {
  source: 'fallback',
  message: 'Downstream call exceeded 1000ms timeout limit. Fallback returned gracefully.',
};

const timeoutFetch = createSmoothFetch<typeof TIMEOUT_FALLBACK>({
  timeoutMs: 1000,
  backoff: {
    baseDelay: 200,
    maxRetries: 2,
  },
  fallback: TIMEOUT_FALLBACK,
});

export async function GET() {
  const startTime = Date.now();
  try {
    const result = await timeoutFetch(SANDBOX_URL, { cache: 'no-store' });
    const durationMs = Date.now() - startTime;

    if (result instanceof Response) {
      const data = await result.json().catch(() => null);
      return Response.json({
        feature: 'timeoutMs',
        source: 'live',
        durationMs,
        status: result.status,
        data,
      });
    }

    return Response.json({
      feature: 'timeoutMs',
      source: 'fallback',
      durationMs,
      note: 'Per-attempt timeout (1000ms) aborted slow request',
      data: result,
    });
  } catch (err) {
    return Response.json(
      {
        feature: 'timeoutMs',
        durationMs: Date.now() - startTime,
        error: err instanceof Error ? err.message : String(err),
      },
      { status: 504 }
    );
  }
}
