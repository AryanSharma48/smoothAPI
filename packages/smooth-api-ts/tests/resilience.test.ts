import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createSmoothFetch } from '../src/index.js';
import { CircuitOpenError } from '../src/types.js';

const BASE = 'http://localhost:3001';

async function reset() {
  await fetch(`${BASE}/reset`);
}

// Tests are sequential — each suite resets the counter before running.

describe('retry logic', () => {
  it('retries on 500 and eventually gets 200', async () => {
    await reset();
    // seq after reset: 1=200, 2=200, 3=500, 4=200, 5=429, 6=500, ...
    // with maxRetries:3 and a lucky sequence we should get through
    const resilientFetch = createSmoothFetch({
      backoff: { baseDelay: 10, maxDelay: 50, maxRetries: 3 },
      circuitBreaker: { failureThreshold: 10, cooldownMs: 60_000 },
      retryOn: [429, 500],
    });

    const res = await resilientFetch(`${BASE}/unstable-data`) as Response;
    assert.ok(res.ok || res.status < 500, 'should eventually get a non-500 response');
  });
});

describe('circuit breaker', () => {
  it('trips to OPEN after failureThreshold consecutive failures', async () => {
    await reset();

    const resilientFetch = createSmoothFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 60_000 },
      retryOn: [500, 429],
      fallback: { tripped: true },
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(null, { status: 500 });

    try {
      const results: (string | number)[] = [];
      for (let i = 0; i < 5; i++) {
        const res = await resilientFetch(`${BASE}/unstable-data`);
        if (res && typeof res === 'object' && 'tripped' in (res as object)) {
          results.push('FALLBACK');
        } else if (res) {
          results.push((res as Response).status);
        } else {
          results.push('NETWORK_ERROR');
        }
      }

      assert.ok(results.includes('FALLBACK'), `circuit should have returned fallback, got: ${JSON.stringify(results)}`);
    } finally {
      globalThis.fetch = originalFetch;
    }

  });

  it('returns fallback immediately when circuit is OPEN', async () => {
    await reset();

    const fallback = { data: 'cached_value' };
    const resilientFetch = createSmoothFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 60_000 },
      retryOn: [500, 429],
      fallback,
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(null, { status: 500 });

    try {
      // Drive failures until circuit trips, then check fallback is returned
      for (let i = 0; i < 5; i++) {
        await resilientFetch(`${BASE}/unstable-data`).catch(() => {});
      }

      // Next call should hit OPEN circuit and get fallback instantly
      const result = await resilientFetch(`${BASE}/unstable-data`);
      assert.deepEqual(result, fallback, 'should return the exact fallback object');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('throws CircuitOpenError when OPEN and no fallback is configured', async () => {
    await reset();

    const resilientFetch = createSmoothFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 60_000 },
      retryOn: [500, 429],
      // no fallback
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(null, { status: 500 });

    try {
      for (let i = 0; i < 5; i++) {
        await resilientFetch(`${BASE}/unstable-data`).catch(() => {});
      }

      await assert.rejects(
        () => resilientFetch(`${BASE}/unstable-data`),
        (err: unknown) => {
          assert.ok(err instanceof CircuitOpenError, `expected CircuitOpenError, got ${err}`);
          assert.ok((err as CircuitOpenError).domain.includes('localhost'));
          return true;
        }
      );
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

describe('circuit breaker recovery', () => {
  it('transitions OPEN → HALF_OPEN → CLOSED after cooldown', async () => {
    await reset();

    const cooldownMs = 500; // short cooldown for testing
    const resilientFetch = createSmoothFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs },
      retryOn: [500, 429],
      fallback: { tripped: true },
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => new Response(null, { status: 500 });

    try {
      // Trip the circuit
      for (let i = 0; i < 5; i++) {
        await resilientFetch(`${BASE}/unstable-data`).catch(() => {});
      }
    } finally {
      globalThis.fetch = originalFetch;
    }

    // Wait for cooldown
    await new Promise(resolve => setTimeout(resolve, cooldownMs + 100));

    // Reset sandbox counter so next request gets a 200
    await reset();

    // Probe request should succeed and close the circuit
    const res = await resilientFetch(`${BASE}/unstable-data`);
    assert.ok(
      res instanceof Response && res.status === 200,
      `expected 200 after recovery, got ${JSON.stringify(res)}`
    );
  });
});

describe('non-retryable error fallback & alerts', () => {
  it('returns normal response without alert when fallbackOnNonRetryable is false', async () => {
    const resilientFetch = createSmoothFetch({
      backoff: { maxRetries: 0 },
      fallbackOnNonRetryable: false,
    });

    const originalFetch = globalThis.fetch;
    let alertCalled = false;
    const mockAlert = () => { alertCalled = true; };
    const originalWindow = (globalThis as any).window;
    (globalThis as any).window = { alert: mockAlert };

    globalThis.fetch = async () => new Response(null, { status: 404, statusText: 'Not Found' });

    try {
      const res = await resilientFetch(`${BASE}/some-url`);
      assert.ok(res instanceof Response);
      assert.equal(res.status, 404);
      assert.equal(alertCalled, false);
    } finally {
      globalThis.fetch = originalFetch;
      (globalThis as any).window = originalWindow;
    }
  });

  it('triggers window.alert and returns mock Response on 405 when fallbackOnNonRetryable is true and no fallback config', async () => {
    const resilientFetch = createSmoothFetch({
      backoff: { maxRetries: 0 },
      fallbackOnNonRetryable: true,
    });

    const originalFetch = globalThis.fetch;
    let alertedMessage = '';
    const mockAlert = (msg: string) => { alertedMessage = msg; };
    const originalWindow = (globalThis as any).window;
    (globalThis as any).window = { alert: mockAlert };

    globalThis.fetch = async () => new Response(null, { status: 405, statusText: 'Method Not Allowed' });

    try {
      const res: any = await resilientFetch(`${BASE}/some-url`);
      assert.ok(res instanceof Response);
      assert.equal(res.status, 405);
      
      const body = await res.json();
      assert.equal(body.error, true);
      assert.equal(body.status, 405);
      assert.ok(body.message.includes('405 Method Not Allowed'));
      assert.ok(alertedMessage.includes('405 Method Not Allowed'));
    } finally {
      globalThis.fetch = originalFetch;
      (globalThis as any).window = originalWindow;
    }
  });

  it('returns configured fallback when fallbackOnNonRetryable is true and fallback is provided', async () => {
    const fallbackVal = { fallbackMsg: 'custom_fallback' };
    const resilientFetch = createSmoothFetch({
      backoff: { maxRetries: 0 },
      fallbackOnNonRetryable: true,
      fallback: fallbackVal,
    });

    const originalFetch = globalThis.fetch;
    let alertCalled = false;
    const mockAlert = () => { alertCalled = true; };
    const originalWindow = (globalThis as any).window;
    (globalThis as any).window = { alert: mockAlert };

    globalThis.fetch = async () => new Response(null, { status: 404, statusText: 'Not Found' });

    try {
      const res = await resilientFetch(`${BASE}/some-url`);
      assert.deepEqual(res, fallbackVal);
      assert.equal(alertCalled, true);
    } finally {
      globalThis.fetch = originalFetch;
      (globalThis as any).window = originalWindow;
    }
  });

  it('calls custom callback instead of window.alert when provided', async () => {
    let callbackArgs: { status: number; msg: string } | unknown;
    const resilientFetch = createSmoothFetch({
      backoff: { maxRetries: 0 },
      fallbackOnNonRetryable: true,
      onNonRetryableError: (status, msg) => {
        callbackArgs = { status, msg };
      },
    });

    const originalFetch = globalThis.fetch;
    let alertCalled = false;
    const mockAlert = () => { alertCalled = true; };
    const originalWindow = (globalThis as any).window;
    (globalThis as any).window = { alert: mockAlert };

    globalThis.fetch = async () => new Response(null, { status: 403, statusText: 'Forbidden' });

    try {
      const res : any = await resilientFetch(`${BASE}/some-url`);
      assert.ok(res instanceof Response);
      assert.equal(res.status, 403);
      assert.equal(alertCalled, false);
      assert.ok(callbackArgs !== null);
      const args = callbackArgs as { status: number; msg: string };
      assert.equal(args.status, 403);
      assert.ok(args.msg.includes('403 Forbidden'));
    } finally {
      globalThis.fetch = originalFetch;
      (globalThis as any).window = originalWindow;
    }
  });
});
