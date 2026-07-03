import test, { describe, it, mock } from 'node:test';
import assert from 'node:assert';
import { createSmoothFetch } from '../src/index.js';

describe('Timeout Functionality', () => {
  test('should abort fetch if timeout is exceeded and trigger retry', async (t) => {
    // We mock global fetch to hang, then succeed
    const originalFetch = global.fetch;
    let callCount = 0;
    
    global.fetch = (async (url: any, options: any) => {
      callCount++;
      if (callCount === 1) {
        return new Promise((resolve, reject) => {
          options?.signal?.addEventListener('abort', () => reject(new DOMException('Request Timeout', 'AbortError')));
        });
      }
      return new Response('OK', { status: 200 });
    }) as any;

    try {
      const smoothFetch = createSmoothFetch({
        timeoutMs: 50,
        backoff: { baseDelay: 10, maxRetries: 1 }
      });

      const promise = smoothFetch('http://example.com/timeout');
      
      const response = await promise as Response;
      assert.strictEqual(response.status, 200);
      assert.strictEqual(callCount, 2);
    } finally {
      global.fetch = originalFetch;
    }
  });

  test('should respect user-provided abort signal', async (t) => {
    const originalFetch = global.fetch;
    let callCount = 0;
    
    global.fetch = (async (url: any, options: any) => {
      callCount++;
      return new Promise((resolve, reject) => {
        options?.signal?.addEventListener('abort', () => reject(new DOMException('User Abort', 'AbortError')));
      });
    }) as any;

    try {
      const smoothFetch = createSmoothFetch({
        timeoutMs: 500,
        backoff: { maxRetries: 1 }
      });

      const controller = new AbortController();
      const promise = smoothFetch('http://example.com/abort', { signal: controller.signal });

      // Immediately abort from the user
      controller.abort();

      await assert.rejects(promise);
      assert.strictEqual(callCount, 1);
    } finally {
      global.fetch = originalFetch;
    }
  });
});
