import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { createSmoothFetch } from '../src/index.js';

const BASE = 'http://localhost:3001';

async function reset() {
  await fetch(`${BASE}/reset`);
}

describe('abort controller', () => {
  it('prevents fetch if already aborted', async () => {
    await reset();
    const fetch = createSmoothFetch({
      backoff: { maxRetries: 3, baseDelay: 10 },
    });

    const controller = new AbortController();
    controller.abort(new Error("Pre-aborted"));

    try {
      await fetch(`${BASE}/always-fail`, {
        signal: controller.signal
      });
      assert.fail('Should have thrown');
    } catch (err: any) {
      assert.strictEqual(err.message, 'Pre-aborted');
    }
  });

  it('halts retry loop and throws when aborted during sleep', async () => {
    await reset();
    // Using a large baseDelay to ensure the abort happens during sleep
    const fetch = createSmoothFetch({
      backoff: { maxRetries: 3, baseDelay: 1000 },
    });

    const controller = new AbortController();
    
    setTimeout(() => {
      controller.abort(new Error("Aborted during sleep"));
    }, 50);

    const startTime = Date.now();
    try {
      await fetch(`${BASE}/always-fail`, {
        signal: controller.signal
      });
      assert.fail('Should have thrown');
    } catch (err: any) {
      const duration = Date.now() - startTime;
      assert.ok(duration < 500, `Should have aborted quickly, took ${duration}ms`);
      assert.strictEqual(err.message, 'Aborted during sleep');
    }
  });
});
