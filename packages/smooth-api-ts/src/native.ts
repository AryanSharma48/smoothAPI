import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

export interface NativeRetryDecision {
  type: string;
  delayMs?: number;
}

export interface INativeCircuitBreaker {
  canRequest(nowMs: number): boolean;
  recordSuccess(): void;
  recordFailure(nowMs: number): void;
  readonly state: string;
  readonly failureCount: number;
}

interface NativeBinding {
  calculateBackoffNative: (attempt: number, baseDelayMs: number, maxDelayMs: number) => number;
  evaluateResponseNative: (
    status: number,
    attempt: number,
    baseDelayMs: number,
    maxDelayMs: number,
    maxRetries?: number | null,
    retryAfterHeader?: string | null,
  ) => NativeRetryDecision;
  NativeCircuitBreaker: new (
    failureThreshold?: number | null,
    cooldownMs?: number | null,
  ) => INativeCircuitBreaker;
}

let native: NativeBinding | null = null;

try {
  native = require('../../../bindings/node');
} catch {
  try {
    native = require('@codingaryan/smoothapi-node');
  } catch {
    native = null;
  }
}

export function isNativeAvailable(): boolean {
  return native !== null;
}

export function calculateBackoffWithNative(attempt: number, base: number, max: number): number {
  if (native) {
    return native.calculateBackoffNative(attempt, base, max);
  }
  return Math.min(max, base * (2 ** attempt));
}

export function evaluateResponseWithNative(
  status: number,
  attempt: number,
  base: number,
  max: number,
  maxRetries: number = 3,
  retryAfter?: string | null,
): NativeRetryDecision {
  if (native) {
    return native.evaluateResponseNative(status, attempt, base, max, maxRetries, retryAfter);
  }

  if (status >= 200 && status < 300) {
    return { type: 'Success' };
  }
  if (![429, 500, 502, 503, 504].includes(status)) {
    return { type: 'Terminal' };
  }
  if (attempt >= maxRetries) {
    return { type: 'Exhausted' };
  }
  let delay = Math.min(max, base * (2 ** attempt));
  if (status === 429 && retryAfter) {
    const parsed = parseInt(retryAfter, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      delay = parsed * 1000;
    }
  }
  return { type: 'Retry', delayMs: delay };
}

export function createCircuitBreaker(
  failureThreshold: number = 3,
  cooldownMs: number = 10_000,
): INativeCircuitBreaker | null {
  if (native) {
    return new native.NativeCircuitBreaker(failureThreshold, cooldownMs);
  }
  return null;
}
