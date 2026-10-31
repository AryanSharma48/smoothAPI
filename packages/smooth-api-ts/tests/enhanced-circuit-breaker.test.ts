import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createSmoothFetch, CircuitBreakerState, CircuitOpenError } from '../src/index.js';

describe('Enhanced Circuit Breaker: Sliding Window & Rate Threshold', () => {
  it('trips OPEN when failure rate exceeds failureRateThreshold', () => {
    const breaker = new CircuitBreakerState({
      failureThreshold: 100, // Make consecutive threshold very high
      failureRateThreshold: 0.5, // 50% failure rate
      windowSize: 10,
      minRequestsInWindow: 4,
    });

    // 2 successes, 1 failure -> 1/3 (33%) -> below minRequests (3 < 4), stays CLOSED
    breaker.recordSuccess('api.example.com');
    breaker.recordSuccess('api.example.com');
    breaker.recordFailure('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'CLOSED');

    // 1 more failure -> 2 failures out of 4 requests (50%) -> trips OPEN!
    breaker.recordFailure('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'OPEN');
  });

  it('does not trip if failure rate is below failureRateThreshold', () => {
    const breaker = new CircuitBreakerState({
      failureThreshold: 100,
      failureRateThreshold: 0.5,
      windowSize: 10,
      minRequestsInWindow: 4,
    });

    // 3 successes, 1 failure -> 25% failure rate -> stays CLOSED
    breaker.recordSuccess('api.example.com');
    breaker.recordSuccess('api.example.com');
    breaker.recordSuccess('api.example.com');
    breaker.recordFailure('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'CLOSED');

    // Another success -> 1 failure out of 5 (20%) -> stays CLOSED
    breaker.recordSuccess('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'CLOSED');
  });
});

describe('Enhanced Circuit Breaker: Anti-Flapping Multi-Probe (successThreshold)', () => {
  it('requires successThreshold consecutive successes in HALF_OPEN to transition to CLOSED', () => {
    const breaker = new CircuitBreakerState({
      failureThreshold: 2,
      cooldownMs: 50,
      successThreshold: 2, // requires 2 consecutive successes
    });

    breaker.recordFailure('api.example.com');
    breaker.recordFailure('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'OPEN');

    // Simulate cooldown passing by setting lastFailureTime in the past
    // Let's use canRequest after cooldown
    const entry = (breaker as any).getOrCreate('api.example.com');
    entry.lastFailureTime = Date.now() - 100;

    // First request enters HALF_OPEN
    assert.equal(breaker.canRequest('api.example.com'), true);
    assert.equal(breaker.getState('api.example.com'), 'HALF_OPEN');

    // 1st successful probe -> should STILL be in HALF_OPEN because successThreshold is 2
    breaker.recordSuccess('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'HALF_OPEN');

    // Next request probes again
    assert.equal(breaker.canRequest('api.example.com'), true);

    // 2nd successful probe -> now closes!
    breaker.recordSuccess('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'CLOSED');
  });

  it('immediately trips back to OPEN if a probe fails during HALF_OPEN', () => {
    const breaker = new CircuitBreakerState({
      failureThreshold: 2,
      cooldownMs: 50,
      successThreshold: 3,
    });

    breaker.recordFailure('api.example.com');
    breaker.recordFailure('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'OPEN');

    const entry = (breaker as any).getOrCreate('api.example.com');
    entry.lastFailureTime = Date.now() - 100;

    // Enter HALF_OPEN
    assert.equal(breaker.canRequest('api.example.com'), true);
    // 1st probe succeeds
    breaker.recordSuccess('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'HALF_OPEN');

    // 2nd probe starts
    assert.equal(breaker.canRequest('api.example.com'), true);
    // 2nd probe FAILS -> immediate trip to OPEN
    breaker.recordFailure('api.example.com');
    assert.equal(breaker.getState('api.example.com'), 'OPEN');
  });

  it('enforces single in-flight probe during HALF_OPEN to prevent thundering herd', () => {
    const breaker = new CircuitBreakerState({
      failureThreshold: 2,
      cooldownMs: 50,
      successThreshold: 2,
    });

    breaker.recordFailure('api.example.com');
    breaker.recordFailure('api.example.com');

    const entry = (breaker as any).getOrCreate('api.example.com');
    entry.lastFailureTime = Date.now() - 100;

    // Caller 1 becomes the probe
    assert.equal(breaker.canRequest('api.example.com'), true);

    // Caller 2 tries concurrently while probe is in flight -> blocked!
    assert.equal(breaker.canRequest('api.example.com'), false);

    // Probe completes
    breaker.recordSuccess('api.example.com');

    // Now caller 3 can probe
    assert.equal(breaker.canRequest('api.example.com'), true);
  });
});

describe('Enhanced Circuit Breaker: Route Partitioning', () => {
  it('isolates failures per route when partitionBy is host-and-path', async () => {
    const smoothFetch = createSmoothFetch({
      backoff: { baseDelay: 1, maxRetries: 0 },
      circuitBreaker: {
        failureThreshold: 2,
        cooldownMs: 60_000,
        partitionBy: 'host-and-path',
      },
      fallback: { fallbackResult: true },
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.includes('/broken-route')) {
        return new Response(null, { status: 500 });
      }
      return new Response(JSON.stringify({ healthy: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    try {
      // 1. Trip the circuit for /broken-route
      await smoothFetch('http://api.example.com/broken-route');
      await smoothFetch('http://api.example.com/broken-route');

      // Next request to /broken-route should receive fallback because circuit is OPEN for that route
      const brokenRes = await smoothFetch('http://api.example.com/broken-route');
      assert.deepEqual(brokenRes, { fallbackResult: true });

      // 2. But requests to /healthy-route on the EXACT SAME HOST should succeed!
      const healthyRes = await smoothFetch('http://api.example.com/healthy-route');
      assert.ok(healthyRes instanceof Response);
      assert.equal(healthyRes.status, 200);
      const data = await (healthyRes as Response).json();
      assert.deepEqual(data, { healthy: true });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('supports custom circuitKeyFn partitioning', async () => {
    const smoothFetch = createSmoothFetch({
      backoff: { baseDelay: 1, maxRetries: 0 },
      circuitBreaker: {
        failureThreshold: 2,
        cooldownMs: 60_000,
        circuitKeyFn: (url) => {
          // Partition by service name parsed from query param or custom logic
          const parsed = new URL(url.toString(), 'http://localhost');
          return parsed.searchParams.get('service') || 'default';
        },
      },
      fallback: { fallbackResult: true },
    });

    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.includes('service=auth')) {
        return new Response(null, { status: 500 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    };

    try {
      // Trip service=auth
      await smoothFetch('http://gateway.internal/api?service=auth');
      await smoothFetch('http://gateway.internal/api?service=auth');

      // service=auth is tripped
      const authRes = await smoothFetch('http://gateway.internal/api?service=auth');
      assert.deepEqual(authRes, { fallbackResult: true });

      // service=billing is healthy and works
      const billingRes = await smoothFetch('http://gateway.internal/api?service=billing');
      assert.ok(billingRes instanceof Response);
      assert.equal(billingRes.status, 200);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

