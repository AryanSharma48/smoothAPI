import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { calculateBackoff } from '../src/utils/backoff.js';

describe('Backoff and Jitter', () => {
  it('respects maximum delay boundaries', () => {
    const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 5 };
    
    for (let i = 0; i < 100; i++) {
      const delay = calculateBackoff(10, config);
      assert.ok(delay <= 5000, `Delay ${delay} exceeded maxDelay 5000`);
      assert.ok(delay >= 0, `Delay ${delay} is negative`);
    }
  });

  it('exhibits full jitter distribution within bounds', () => {
    const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 3 };
    
    const delays = new Set<number>();
    
    for (let i = 0; i < 20; i++) {
      const delay = calculateBackoff(2, config);
      assert.ok(delay <= 400, `Delay ${delay} exceeded calculated cap 400`);
      delays.add(delay);
    }
    
    assert.ok(delays.size > 1, 'Jitter did not produce variable delays');
  });
});
