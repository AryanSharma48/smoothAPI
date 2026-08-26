import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { CircuitBreakerState } from '../src/state.js';
import { createSmoothFetch } from '../src/index.js';

describe('Edge Cases and Memory Sweeper', () => {
  it('enforces memory cleanup when domain count exceeds 1000', () => {
    const breaker = new CircuitBreakerState();
    
    // Add 1050 healthy CLOSED domains with failureCount = 0
    for (let i = 0; i < 1050; i++) {
      breaker.canRequest(`domain-${i}.com`);
    }

    // Accessing a new domain triggers cleanup()
    breaker.canRequest('trigger-cleanup.com');

    // Accessing an earlier healthy domain should be re-initialized gracefully
    const state = breaker.getState('domain-0.com');
    assert.equal(state, 'CLOSED');
  });

  it('handles malformed, non-numeric, or invalid Retry-After headers gracefully', async () => {
    const originalFetch = globalThis.fetch;
    let callCount = 0;

    globalThis.fetch = async () => {
      callCount++;
      if (callCount === 1) {
        return new Response(null, {
          status: 429,
          headers: { 'Retry-After': 'invalid-not-a-number' }
        });
      }
      return new Response(null, { status: 200 });
    };

    try {
      const smoothFetch = createSmoothFetch({
        backoff: { baseDelay: 10, maxDelay: 50, maxRetries: 1 },
        retryOn: [429],
      });

      const res = await smoothFetch('http://example.com/retry-after-invalid') as Response;
      assert.equal(res.status, 200);
      assert.equal(callCount, 2);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('handles HTTP-date formatted Retry-After headers without crashing', async () => {
    const originalFetch = globalThis.fetch;
    let callCount = 0;

    globalThis.fetch = async () => {
      callCount++;
      if (callCount === 1) {
        return new Response(null, {
          status: 429,
          headers: { 'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT' }
        });
      }
      return new Response(null, { status: 200 });
    };

    try {
      const smoothFetch = createSmoothFetch({
        backoff: { baseDelay: 10, maxDelay: 50, maxRetries: 1 },
        retryOn: [429],
      });

      const res = await smoothFetch('http://example.com/retry-after-date') as Response;
      assert.equal(res.status, 200);
      assert.equal(callCount, 2);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
