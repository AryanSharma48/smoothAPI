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

  describe('jitter: none', () => {
    it('returns deterministic capped exponential delay with no randomness', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 5, jitter: 'none' as const };
      
      const delay1 = calculateBackoff(3, config);
      const delay2 = calculateBackoff(3, config);
      assert.strictEqual(delay1, delay2, 'none strategy should be deterministic');
      
      const expected = Math.min(5000, 100 * (2 ** 3));
      assert.strictEqual(delay1, expected);
    });

    it('respects maxDelay cap', () => {
      const config = { baseDelay: 1000, maxDelay: 3000, maxRetries: 10, jitter: 'none' as const };
      const delay = calculateBackoff(10, config);
      assert.strictEqual(delay, 3000);
    });
  });

  describe('jitter: full', () => {
    it('produces values between 0 and capped delay', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 5, jitter: 'full' as const };
      
      for (let i = 0; i < 100; i++) {
        const delay = calculateBackoff(3, config);
        assert.ok(delay >= 0, `Delay ${delay} is negative`);
        assert.ok(delay <= 800, `Delay ${delay} exceeded capped value 800`);
      }
    });

    it('produces variable delays across calls', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 3, jitter: 'full' as const };
      const delays = new Set<number>();
      
      for (let i = 0; i < 20; i++) {
        delays.add(calculateBackoff(2, config));
      }
      
      assert.ok(delays.size > 1, 'Full jitter did not produce variable delays');
    });
  });

  describe('jitter: equal', () => {
    it('produces values at least half of capped delay', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 5, jitter: 'equal' as const };
      
      for (let i = 0; i < 100; i++) {
        const delay = calculateBackoff(3, config);
        assert.ok(delay >= 400, `Delay ${delay} was below half of capped 800`);
        assert.ok(delay <= 800, `Delay ${delay} exceeded capped value 800`);
      }
    });

    it('is used as the default when jitter is not specified', () => {
      const configWithDefault = { baseDelay: 100, maxDelay: 5000, maxRetries: 5 };
      const configExplicit = { ...configWithDefault, jitter: 'equal' as const };
      
      const delay1 = calculateBackoff(3, configWithDefault);
      const delay2 = calculateBackoff(3, configExplicit);
      
      // Both should stay within the same equal-jitter bounds
      assert.ok(delay1 >= 400 && delay1 <= 800);
      assert.ok(delay2 >= 400 && delay2 <= 800);
    });
  });

  describe('jitter: decorrelated', () => {
    it('stays within [0, maxDelay] bounds', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 10, jitter: 'decorrelated' as const };
      
      let prevDelay: number | undefined;
      for (let i = 0; i < 100; i++) {
        const delay = calculateBackoff(i, config, prevDelay);
        assert.ok(delay >= 0, `Delay ${delay} is negative`);
        assert.ok(delay <= 5000, `Delay ${delay} exceeded maxDelay 5000`);
        prevDelay = delay;
      }
    });

    it('produces variable delays across calls', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 5, jitter: 'decorrelated' as const };
      const delays = new Set<number>();
      
      let prevDelay: number | undefined;
      for (let i = 0; i < 20; i++) {
        const delay = calculateBackoff(2, config, prevDelay);
        delays.add(delay);
        prevDelay = delay;
      }
      
      assert.ok(delays.size > 1, 'Decorrelated jitter did not produce variable delays');
    });

    it('falls back to baseDelay when no prevDelay is provided', () => {
      const config = { baseDelay: 100, maxDelay: 5000, maxRetries: 5, jitter: 'decorrelated' as const };
      const delay = calculateBackoff(0, config);
      assert.ok(delay >= 100, `Delay ${delay} should be at least baseDelay 100`);
      assert.ok(delay <= 5000);
    });
  });
});