import { describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';
import { createSmoothFetch } from '../src/index.js';
import type { CircuitStateChangeEvent, RetryContext } from '../src/types.js';

const BASE = 'http://localhost:3001';

async function reset() {
  await fetch(`${BASE}/reset`);
}

// Ensure sleep completes quickly for tests where appropriate
const backoffConfig = { maxRetries: 3, baseDelay: 10, maxDelay: 50 };

describe('Lifecycle Event Hooks', () => {
  it('onRetry fires with correct context on retryable HTTP error', async () => {
    await reset();
    const mockOnRetry = mock.fn((ctx: RetryContext) => {});
    
    const fetch = createSmoothFetch({
      backoff: backoffConfig,
      onRetry: mockOnRetry
    } as any); // Type cast temporarily until types are updated

    try {
      await fetch(`${BASE}/always-fail`);
    } catch (e) {
      // Expected to fail after exhausting retries
    }

    assert.strictEqual(mockOnRetry.mock.calls.length, 3, 'onRetry should be called 3 times');
    
    const firstCallArgs = mockOnRetry.mock.calls[0].arguments[0] as RetryContext;
    assert.strictEqual(firstCallArgs.attempt, 1);
    assert.strictEqual(firstCallArgs.maxRetries, 3);
    assert.ok(firstCallArgs.delayMs >= 0, 'delayMs should be >= 0');
    assert.strictEqual(firstCallArgs.status, 500);
    assert.strictEqual(firstCallArgs.error, undefined);
    assert.ok(firstCallArgs.url.includes('/always-fail'));
    assert.strictEqual(firstCallArgs.domain, 'localhost');
  });

  it('onCircuitStateChange fires for CLOSED -> OPEN -> HALF_OPEN -> CLOSED transitions', async () => {
    await reset();
    const mockOnChange = mock.fn((event: CircuitStateChangeEvent) => {});
    
    // Very short cooldown to test HALF_OPEN quickly
    const fetch = createSmoothFetch({
      backoff: { maxRetries: 0, baseDelay: 10 },
      circuitBreaker: { failureThreshold: 2, cooldownMs: 50 },
      onCircuitStateChange: mockOnChange
    } as any);

    // 1st failure (failureCount: 1) -> No state change (stays CLOSED)
    try { await fetch(`${BASE}/always-fail`); } catch (e) {}
    assert.strictEqual(mockOnChange.mock.calls.length, 0);

    // 2nd failure (failureCount: 2) -> Exceeds threshold -> OPEN
    try { await fetch(`${BASE}/always-fail`); } catch (e) {}
    assert.strictEqual(mockOnChange.mock.calls.length, 1);
    let event = mockOnChange.mock.calls[0].arguments[0] as CircuitStateChangeEvent;
    assert.deepEqual(event, { domain: 'localhost', from: 'CLOSED', to: 'OPEN', failureCount: 2 });

    // Wait for cooldown
    await new Promise(r => setTimeout(r, 60));

    // 3rd attempt: Probes HALF_OPEN, but fails again -> OPEN
    try { await fetch(`${BASE}/always-fail`); } catch (e) {}
    assert.strictEqual(mockOnChange.mock.calls.length, 3);
    
    // Check transition to HALF_OPEN
    event = mockOnChange.mock.calls[1].arguments[0] as CircuitStateChangeEvent;
    assert.deepEqual(event, { domain: 'localhost', from: 'OPEN', to: 'HALF_OPEN', failureCount: 2 });
    
    // Check transition back to OPEN due to probe failure
    event = mockOnChange.mock.calls[2].arguments[0] as CircuitStateChangeEvent;
    assert.deepEqual(event, { domain: 'localhost', from: 'HALF_OPEN', to: 'OPEN', failureCount: 3 });

    // Wait for cooldown again
    await new Promise(r => setTimeout(r, 60));
    
    // Reset the server so the next attempt succeeds
    await reset();

    // 4th attempt: Probes HALF_OPEN, succeeds -> CLOSED
    await fetch(`${BASE}/flaky`);
    assert.strictEqual(mockOnChange.mock.calls.length, 5);
    
    event = mockOnChange.mock.calls[3].arguments[0] as CircuitStateChangeEvent;
    assert.deepEqual(event, { domain: 'localhost', from: 'OPEN', to: 'HALF_OPEN', failureCount: 3 });
    
    event = mockOnChange.mock.calls[4].arguments[0] as CircuitStateChangeEvent;
    assert.deepEqual(event, { domain: 'localhost', from: 'HALF_OPEN', to: 'CLOSED', failureCount: 0 });
  });

  it('exceptions thrown in hooks do not crash the request pipeline (Fail-Safe)', async () => {
    await reset();
    let retryCalled = false;
    let stateChangeCalled = false;
    
    const fetch = createSmoothFetch({
      backoff: { maxRetries: 1, baseDelay: 10 },
      circuitBreaker: { failureThreshold: 1, cooldownMs: 1000 },
      onRetry: () => {
        retryCalled = true;
        throw new Error('User bug in onRetry');
      },
      onCircuitStateChange: () => {
        stateChangeCalled = true;
        throw new Error('User bug in onCircuitStateChange');
      }
    } as any);

    // Ensure we can still complete the fetch flow without crashing
    let response: any;
    try {
      response = await fetch(`${BASE}/always-fail`);
    } catch (e: any) {
      assert.fail(`Should not have thrown: ${e.message}`);
    }

    assert.strictEqual(response.status, 500, 'Should have returned the 500 response without crashing');
    assert.ok(retryCalled, 'onRetry should have been invoked');
    assert.ok(stateChangeCalled, 'onCircuitStateChange should have been invoked');
  });

  it('onSuccess fires on clean 200 response with correct context', async () => {
    await reset();
    const mockSuccess = mock.fn();
    const mockFailure = mock.fn();

    const fetch = createSmoothFetch<Response>({
      onSuccess: mockSuccess,
      onFailure: mockFailure,
    });

    const res = await fetch(`${BASE}/health`) as Response;
    assert.strictEqual(res.status, 200);
    assert.strictEqual(mockSuccess.mock.calls.length, 1);
    assert.strictEqual(mockFailure.mock.calls.length, 0);

    const ctx = mockSuccess.mock.calls[0].arguments[0];
    assert.strictEqual(ctx.status, 200);
    assert.strictEqual(ctx.attempts, 1);
    assert.ok(ctx.durationMs >= 0);
    assert.strictEqual(ctx.domain, 'localhost');
    assert.ok(ctx.url.includes('/health'));
  });

  it('onSuccess fires after retries succeed', async () => {
    await reset();
    const mockSuccess = mock.fn();
    const mockRetry = mock.fn();

    const fetch = createSmoothFetch<Response>({
      backoff: { maxRetries: 3, baseDelay: 10, maxDelay: 50 },
      onRetry: mockRetry,
      onSuccess: mockSuccess,
    });

    // /unstable-data: request 1 (200), request 2 (200), request 3 (500), request 4 (200)
    // Make 2 calls first so the next call hits 500 and retries
    await fetch(`${BASE}/unstable-data`); // req 1 -> 200
    await fetch(`${BASE}/unstable-data`); // req 2 -> 200

    mockSuccess.mock.resetCalls();
    // req 3 is 500, retries to req 4 which is 200!
    const res = await fetch(`${BASE}/unstable-data`) as Response;
    assert.strictEqual(res.status, 200);
    assert.strictEqual(mockRetry.mock.calls.length, 1);
    assert.strictEqual(mockSuccess.mock.calls.length, 1);

    const ctx = mockSuccess.mock.calls[0].arguments[0];
    assert.strictEqual(ctx.status, 200);
    assert.strictEqual(ctx.attempts, 2); // 1 initial + 1 retry
  });

  it('onFailure fires when retries are exhausted on 500 (500 should be failure)', async () => {
    await reset();
    const mockSuccess = mock.fn();
    const mockFailure = mock.fn();

    const fetch = createSmoothFetch<Response>({
      backoff: { maxRetries: 2, baseDelay: 10, maxDelay: 50 },
      onSuccess: mockSuccess,
      onFailure: mockFailure,
    });

    const res = await fetch(`${BASE}/always-fail`) as Response;
    assert.strictEqual(res.status, 500);
    assert.strictEqual(mockSuccess.mock.calls.length, 0, 'onSuccess must NOT fire for 500');
    assert.strictEqual(mockFailure.mock.calls.length, 1, 'onFailure must fire for 500');

    const ctx = mockFailure.mock.calls[0].arguments[0];
    assert.strictEqual(ctx.status, 500);
    assert.strictEqual(ctx.attempts, 3); // attempt 0, 1, 2
    assert.strictEqual(ctx.isCircuitOpen, false);
    assert.ok(ctx.durationMs >= 0);
  });

  it('onFailure fires on CircuitOpenError without network IO', async () => {
    await reset();
    const mockFailure = mock.fn();

    const fetch = createSmoothFetch<Response>({
      backoff: { maxRetries: 0, baseDelay: 10 },
      circuitBreaker: { failureThreshold: 1, cooldownMs: 1000 },
      onFailure: mockFailure,
    });

    // Trip circuit
    await fetch(`${BASE}/always-fail`);
    assert.strictEqual(mockFailure.mock.calls.length, 1);

    // Call again while circuit is OPEN
    mockFailure.mock.resetCalls();
    try {
      await fetch(`${BASE}/always-fail`);
      assert.fail('Should throw CircuitOpenError');
    } catch (e: any) {
      assert.strictEqual(e.name, 'CircuitOpenError');
    }

    assert.strictEqual(mockFailure.mock.calls.length, 1);
    const ctx = mockFailure.mock.calls[0].arguments[0];
    assert.strictEqual(ctx.isCircuitOpen, true);
    assert.strictEqual(ctx.attempts, 0);
  });

  it('exceptions in onSuccess and onFailure do not crash the request pipeline', async () => {
    await reset();
    const fetch = createSmoothFetch<Response>({
      onSuccess: () => {
        throw new Error('User bug in onSuccess');
      },
      onFailure: () => {
        throw new Error('User bug in onFailure');
      },
    });

    // Should succeed despite error in onSuccess
    const res = await fetch(`${BASE}/health`) as Response;
    assert.strictEqual(res.status, 200);

    // Should return 500 despite error in onFailure
    const failRes = await fetch(`${BASE}/always-fail`) as Response;
    assert.strictEqual(failRes.status, 500);
  });
});

