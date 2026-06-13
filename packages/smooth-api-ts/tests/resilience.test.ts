import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createResilientFetch } from '../src/index.js';
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
    const resilientFetch = createResilientFetch({
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

    const resilientFetch = createResilientFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 60_000 },
      retryOn: [500, 429],
      fallback: { tripped: true },
    });

    const results: (string | number)[] = [];
    for (let i = 0; i < 7; i++) {
      const res = await resilientFetch(`${BASE}/unstable-data`);
      if (res && typeof res === 'object' && 'tripped' in (res as object)) {
        results.push('FALLBACK');
      } else {
        results.push((res as Response).status);
      }
    }

    assert.ok(results.includes('FALLBACK'), `circuit should have returned fallback, got: ${JSON.stringify(results)}`);
  });

  it('returns fallback immediately when circuit is OPEN', async () => {
    await reset();

    const fallback = { data: 'cached_value' };
    const resilientFetch = createResilientFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 60_000 },
      retryOn: [500, 429],
      fallback,
    });

    // Drive failures until circuit trips, then check fallback is returned
    for (let i = 0; i < 6; i++) {
      await resilientFetch(`${BASE}/unstable-data`).catch(() => {});
    }

    // Next call should hit OPEN circuit and get fallback instantly
    const result = await resilientFetch(`${BASE}/unstable-data`);
    assert.deepEqual(result, fallback, 'should return the exact fallback object');
  });

  it('throws CircuitOpenError when OPEN and no fallback is configured', async () => {
    await reset();

    const resilientFetch = createResilientFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 60_000 },
      retryOn: [500, 429],
      // no fallback
    });

    for (let i = 0; i < 6; i++) {
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
  });
});

describe('circuit breaker recovery', () => {
  it('transitions OPEN → HALF_OPEN → CLOSED after cooldown', async () => {
    await reset();

    const cooldownMs = 500; // short cooldown for testing
    const resilientFetch = createResilientFetch({
      backoff: { baseDelay: 5, maxDelay: 20, maxRetries: 0 },
      circuitBreaker: { failureThreshold: 3, cooldownMs },
      retryOn: [500, 429],
      fallback: { tripped: true },
    });

    // Trip the circuit
    for (let i = 0; i < 9; i++) {
      await resilientFetch(`${BASE}/unstable-data`).catch(() => {});
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
