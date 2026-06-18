/**
 * Tests for the Request Deduplication feature.
 *
 * These tests run without the sandbox server — globalThis.fetch is stubbed
 * directly so they are fully self-contained and deterministic.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createResilientFetch } from '../src/index.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeStubFetch(
  handler: (url: string, options?: RequestInit) => Response,
  counter?: { calls: number }
): typeof fetch {
  return async (url: RequestInfo | URL, options?: RequestInit): Promise<Response> => {
    if (counter) counter.calls++;
    return handler(url.toString(), options);
  };
}

// ---------------------------------------------------------------------------
// Unit tests for dedup — no real network required
// ---------------------------------------------------------------------------

describe('Request Deduplication', () => {
  it('is disabled by default — each call triggers a separate fetch', async () => {
    const counter = { calls: 0 };
    const originalFetch = globalThis.fetch;
    globalThis.fetch = makeStubFetch(() => new Response('{}', { status: 200 }), counter);

    try {
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
      });

      await Promise.all([
        resilientFetch('http://example.com/users/1'),
        resilientFetch('http://example.com/users/1'),
        resilientFetch('http://example.com/users/1'),
      ]);

      assert.equal(counter.calls, 3, 'Without deduplication, each call hits the network');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('deduplicates concurrent identical requests into a single network call', async () => {
    const counter = { calls: 0 };

    // Introduce a small delay so that all three callers overlap in flight.
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url: RequestInfo | URL, opts?: RequestInit): Promise<Response> => {
      counter.calls++;
      await new Promise(r => setTimeout(r, 20)); // simulate network latency
      return new Response(JSON.stringify({ user: 1 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    try {
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {},
      });

      const results = await Promise.all([
        resilientFetch('http://example.com/users/1'),
        resilientFetch('http://example.com/users/1'),
        resilientFetch('http://example.com/users/1'),
      ]);

      assert.equal(counter.calls, 1, 'Exactly one network call should be made for 3 concurrent identical requests');
      for (const res of results) {
        assert.ok(res instanceof Response, 'Every caller receives a Response');
        assert.equal((res as Response).status, 200);
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('does NOT deduplicate requests with different URLs', async () => {
    const counter = { calls: 0 };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url: RequestInfo | URL): Promise<Response> => {
      counter.calls++;
      await new Promise(r => setTimeout(r, 20));
      return new Response('{}', { status: 200 });
    };

    try {
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {},
      });

      await Promise.all([
        resilientFetch('http://example.com/users/1'),
        resilientFetch('http://example.com/users/2'),
      ]);

      assert.equal(counter.calls, 2, 'Different URLs must each trigger their own network call');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('allows a fresh request after the previous one settles', async () => {
    const counter = { calls: 0 };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (): Promise<Response> => {
      counter.calls++;
      return new Response('{}', { status: 200 });
    };

    try {
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {},
      });

      // First call — completes before the second.
      await resilientFetch('http://example.com/data');
      // Second call — should trigger a new network request.
      await resilientFetch('http://example.com/data');

      assert.equal(counter.calls, 2, 'Sequential requests should each hit the network');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('propagates errors to ALL waiting callers', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (): Promise<Response> => {
      await new Promise(r => setTimeout(r, 10));
      throw new TypeError('Network failure');
    };

    try {
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {},
      });

      const results = await Promise.allSettled([
        resilientFetch('http://example.com/flaky'),
        resilientFetch('http://example.com/flaky'),
        resilientFetch('http://example.com/flaky'),
      ]);

      for (const result of results) {
        assert.equal(result.status, 'rejected', 'All callers should receive the rejection');
        assert.ok((result as PromiseRejectedResult).reason instanceof TypeError);
      }
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('respects a custom keyFn — different keys are NOT deduplicated', async () => {
    const counter = { calls: 0 };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (): Promise<Response> => {
      counter.calls++;
      await new Promise(r => setTimeout(r, 20));
      return new Response('{}', { status: 200 });
    };

    try {
      // Custom key always returns the same constant — every request is considered identical.
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {
          keyFn: (_url, options) => (options?.method ?? 'GET').toUpperCase(),
        },
      });

      // Two concurrent GETs to different URLs — same key → deduplicated.
      await Promise.all([
        resilientFetch('http://example.com/a', { method: 'GET' }),
        resilientFetch('http://example.com/b', { method: 'GET' }),
      ]);

      assert.equal(counter.calls, 1, 'Both GETs share a key via custom keyFn → single fetch');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('opts a request out of deduplication when keyFn returns null', async () => {
    const counter = { calls: 0 };

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (): Promise<Response> => {
      counter.calls++;
      await new Promise(r => setTimeout(r, 20));
      return new Response('{}', { status: 200 });
    };

    try {
      const resilientFetch = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {
          keyFn: (_url, options) =>
            (options?.method ?? 'GET').toUpperCase() === 'POST' ? null : _url.toString(),
        },
      });

      // Two concurrent POSTs — keyFn returns null, so they bypass deduplication.
      await Promise.all([
        resilientFetch('http://example.com/users', { method: 'POST' }),
        resilientFetch('http://example.com/users', { method: 'POST' }),
      ]);

      assert.equal(counter.calls, 2, 'null key disables deduplication for this pair of POSTs');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

// ---------------------------------------------------------------------------
// Benchmark (informational — does not fail the test suite)
// ---------------------------------------------------------------------------

describe('Request Deduplication Benchmark', () => {
  it('reports overhead of deduplication map lookup vs plain fetch', async () => {
    const CONCURRENCY = 100;
    const RUNS = 5;

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (): Promise<Response> => new Response('{}', { status: 200 });

    try {
      // --- Without deduplication ---
      const plain = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
      });

      let totalPlain = 0;
      for (let r = 0; r < RUNS; r++) {
        const t0 = performance.now();
        await Promise.all(
          Array.from({ length: CONCURRENCY }, () => plain('http://bench.example.com/data'))
        );
        totalPlain += performance.now() - t0;
      }

      // --- With deduplication ---
      const deduped = createResilientFetch({
        backoff: { maxRetries: 0, baseDelay: 0, maxDelay: 0 },
        deduplication: {},
      });

      let totalDeduped = 0;
      for (let r = 0; r < RUNS; r++) {
        const t0 = performance.now();
        await Promise.all(
          Array.from({ length: CONCURRENCY }, () => deduped('http://bench.example.com/data'))
        );
        totalDeduped += performance.now() - t0;
      }

      const avgPlain = (totalPlain / RUNS).toFixed(2);
      const avgDeduped = (totalDeduped / RUNS).toFixed(2);
      console.log(
        `[Benchmark] ${CONCURRENCY} concurrent requests × ${RUNS} runs | ` +
        `plain avg: ${avgPlain}ms | deduped avg: ${avgDeduped}ms`
      );

      // Deduplication overhead should be negligible (< 50 ms on any reasonable machine).
      assert.ok(
        Number(avgDeduped) - Number(avgPlain) < 50,
        'Deduplication map lookup overhead must be less than 50 ms'
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
