export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

/**
 * Optional function that derives a cache key from a request.
 * Defaults to `url.toString()` when not provided.
 * Return `null` to opt this specific request out of deduplication.
 */
export type DeduplicationKeyFn = (
  url: string | URL,
  options?: RequestInit
) => string | null;

export interface DeduplicationConfig {
  /**
   * Custom function to compute the deduplication key.
   * Receives the same (url, options) passed to resilientFetch.
   * Defaults to the stringified URL (method-agnostic).
   */
  keyFn?: DeduplicationKeyFn;
}

// Per-domain runtime entry stored in the state map.
export interface CircuitEntry {
  state: CircuitState;
  failureCount: number;
  lastFailureTime: number; // epoch ms, used to compute cooldown expiry
}

export interface BackoffConfig {
  baseDelay: number;  // ms, doubles each attempt before jitter
  maxDelay: number;   // ceiling on the pre-jitter exponential
  maxRetries: number;
}

export interface CircuitBreakerConfig {
  failureThreshold: number; // consecutive failures to trip OPEN
  cooldownMs: number;       // time in OPEN before probing with HALF_OPEN
}

// T types the fallback payload so callers get inference at the use site.
export interface ResilientFetchConfig<T = unknown> {
  backoff?: Partial<BackoffConfig>;
  circuitBreaker?: Partial<CircuitBreakerConfig>;
  fallback?: T;    // returned immediately on an OPEN circuit, no network IO
  retryOn?: number[]; // defaults applied in index.ts
  fallbackOnNonRetryable?: boolean;
  onNonRetryableError?: (status: number, message: string) => void;
  /**
   * When set, enables request deduplication.
   * Pass an empty object `{}` to activate with the default key function.
   */
  deduplication?: DeduplicationConfig;
}

// Thrown when the circuit is OPEN and no fallback is configured.
export class CircuitOpenError extends Error {
  readonly domain: string;

  constructor(domain: string) {
    super(`Circuit breaker is OPEN for domain: ${domain}`);
    this.name = 'CircuitOpenError';
    this.domain = domain;
    // Fixes instanceof checks when output is downleveled past ES2022.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
