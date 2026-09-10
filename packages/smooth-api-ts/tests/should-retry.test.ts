import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createSmoothFetch, ShouldRetryPredicate } from '../src/index.js';

const BASE = 'http://localhost:3001';

async function reset() {
  await fetch(`${BASE}/reset`);
}

const fastBackoff = { maxRetries: 2, baseDelay: 10, maxDelay: 50 };

describe('shouldRetry predicate', () => {
  it('triggers custom retry on GraphQL error body with HTTP 200 without consuming caller body', async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        callCount++;
        if (callCount === 1) {
          return new Response(JSON.stringify({ errors: [{ message: 'Rate limited by GraphQL service' }] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ data: { user: 'Alice' } }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      };

      const smoothFetch = createSmoothFetch({
        backoff: fastBackoff,
        shouldRetry: async (response) => {
          if (!response || response.status !== 200) return false;
          const body = await response.json().catch(() => null);
          return Boolean(body && Array.isArray(body.errors) && body.errors.length > 0);
        },
      });

      const res = await smoothFetch('http://example.com/graphql');
      assert.ok(res instanceof Response);
      assert.strictEqual(res.status, 200);
      assert.strictEqual(callCount, 2, 'Should have retried once after first GraphQL error');

      // Crucial: Caller can still read response body because predicate used cloned response
      const data = await res.json();
      assert.deepStrictEqual(data, { data: { user: 'Alice' } });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('bypasses retry when shouldRetry returns false even for a 500 error', async () => {
    await reset();
    let retryCalls = 0;

    const smoothFetch = createSmoothFetch({
      backoff: fastBackoff,
      onRetry: () => { retryCalls++; },
      shouldRetry: (response) => {
        // Explicitly bypass retries for 500 status
        if (response?.status === 500) {
          return false;
        }
        return true;
      },
    });

    const res = await smoothFetch(`${BASE}/always-fail`);
    assert.ok(res instanceof Response);
    assert.strictEqual(res.status, 500);
    assert.strictEqual(retryCalls, 0, 'Should not trigger any retries');
  });

  it('supports asynchronous predicates returning Promise<boolean>', async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        callCount++;
        if (callCount < 3) {
          return new Response('Transient glitch', { status: 503 });
        }
        return new Response('Success', { status: 200 });
      };

      const shouldRetry: ShouldRetryPredicate = async (response) => {
        await new Promise((resolve) => setTimeout(resolve, 5));
        return response?.status === 503;
      };

      const smoothFetch = createSmoothFetch({
        backoff: fastBackoff,
        shouldRetry,
      });

      const res = await smoothFetch('http://example.com/async-check');
      assert.ok(res instanceof Response);
      assert.strictEqual(res.status, 200);
      assert.strictEqual(callCount, 3);
      assert.strictEqual(await res.text(), 'Success');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('handles exceptions thrown inside shouldRetry safely without crashing (Fail-Safe)', async () => {
    const originalError = console.error;
    let loggedError = false;
    console.error = (...args) => {
      loggedError = true;
    };

    let callCount = 0;
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        callCount++;
        if (callCount === 1) {
          return new Response('Internal Server Error', { status: 500 });
        }
        return new Response('Recovered', { status: 200 });
      };

      const smoothFetch = createSmoothFetch({
        backoff: fastBackoff,
        shouldRetry: () => {
          throw new Error('Bug inside custom predicate!');
        },
      });

      const res = await smoothFetch('http://example.com/fail-safe');
      assert.ok(res instanceof Response);
      assert.strictEqual(res.status, 200);
      assert.strictEqual(callCount, 2);
      assert.strictEqual(loggedError, true);
    } finally {
      console.error = originalError;
      globalThis.fetch = originalFetch;
    }
  });

  it('evaluates shouldRetry on network errors and bypasses retry when predicate returns false', async () => {
    let callCount = 0;
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = async () => {
        callCount++;
        throw new TypeError('Network connection refused');
      };

      const smoothFetch = createSmoothFetch({
        backoff: fastBackoff,
        shouldRetry: (_response, error) => {
          if (error instanceof TypeError && error.message.includes('connection refused')) {
            return false;
          }
          return true;
        },
      });

      await assert.rejects(
        async () => {
          await smoothFetch('http://example.com/fatal-network');
        },
        (err) => {
          assert.ok(err instanceof TypeError);
          assert.strictEqual(err.message, 'Network connection refused');
          return true;
        }
      );

      assert.strictEqual(callCount, 1, 'Should have failed immediately without retries');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
