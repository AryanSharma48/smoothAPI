import { createSmoothFetch, type RetryContext } from '@codingaryan/smoothapi';

export const dynamic = 'force-dynamic';

const SANDBOX_URL = 'http://localhost:3001/unstable-data';

export async function GET() {
  const retryHistory: Array<{ attempt: number; delayMs: number }> = [];

  const backoffFetch = createSmoothFetch({
    backoff: {
      baseDelay: 200,
      maxDelay: 3000,
      maxRetries: 3,
      jitter: 'equal',
    },
    retryOn: [429, 500, 502, 503, 504],
    onRetry: (ctx: RetryContext) => {
      retryHistory.push({ attempt: ctx.attempt, delayMs: Math.round(ctx.delayMs) });
    },
  });

  const startTime = Date.now();
  try {
    const result = await backoffFetch(SANDBOX_URL, { cache: 'no-store' });
    const durationMs = Date.now() - startTime;

    if (result instanceof Response) {
      const data = await result.json().catch(() => null);
      return Response.json({
        feature: 'exponential_backoff_jitter',
        status: result.status,
        durationMs,
        retriesPerformed: retryHistory.length,
        retryHistory,
        data,
      });
    }

    return Response.json({
      feature: 'exponential_backoff_jitter',
      source: 'fallback',
      durationMs,
      retriesPerformed: retryHistory.length,
      retryHistory,
      data: result,
    });
  } catch (err) {
    return Response.json(
      {
        feature: 'exponential_backoff_jitter',
        durationMs: Date.now() - startTime,
        retriesPerformed: retryHistory.length,
        retryHistory,
        error: err instanceof Error ? err.message : String(err),
      },
      { status: 502 }
    );
  }
}
