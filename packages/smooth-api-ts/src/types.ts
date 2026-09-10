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
   * Receives the same (url, options) passed to smoothFetch.
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
  jitter?: 'full' | 'equal' | 'decorrelated' | 'none';
}

export interface CircuitBreakerConfig {
  failureThreshold: number; // consecutive failures to trip OPEN
  cooldownMs: number;       // time in OPEN before probing with HALF_OPEN
}

export interface RetryContext {
  attempt: number;
  maxRetries: number;
  delayMs: number;
  error?: Error;
  status?: number;
  url: string;
  domain: string;
}

export interface CircuitStateChangeEvent {
  domain: string;
  from: CircuitState;
  to: CircuitState;
  failureCount: number;
}

/**
 * Custom predicate function to determine if an attempt should be retried.
 * Receives either (response, undefined) on HTTP completion or (undefined, error) on network/catch errors.
 * Returning `true` triggers the backoff/retry loop; returning `false` bypasses retries immediately.
 */
export type ShouldRetryPredicate = (
  response?: Response,
  error?: unknown
) => boolean | Promise<boolean>;

// T types the fallback payload so callers get inference at the use site.
export interface SmoothFetchConfig<T = unknown> {
  backoff?: Partial<BackoffConfig>;
  circuitBreaker?: Partial<CircuitBreakerConfig>;
  fallback?: T;    // returned immediately on an OPEN circuit, no network IO
  retryOn?: number[]; // defaults applied in index.ts
  fallbackOnNonRetryable?: boolean;
  onNonRetryableError?: (status: number, message: string) => void;
  /**
   * Optional custom predicate to determine whether an attempt should be retried.
   * If provided, evaluated alongside or in place of retryOn status checks.
   * Return true to retry, or false to bypass retries immediately.
   */
  shouldRetry?: ShouldRetryPredicate;
  /**
   * When set, enables request deduplication.
   * Pass an empty object `{}` to activate with the default key function.
   */
  deduplication?: DeduplicationConfig;
  /**
   * Maximum duration in milliseconds before a request attempt is aborted.
   * Applied per-attempt. If aborted, the request is considered a failure and may be retried.
   * Must be a positive finite number.
   */
  timeoutMs?: number;
  onRetry?: (context: RetryContext) => void | Promise<void>;
  onCircuitStateChange?: (event: CircuitStateChangeEvent) => void | Promise<void>;
}

/** @deprecated use SmoothFetchConfig instead */
export type ResilientFetchConfig<T = unknown> = SmoothFetchConfig<T>;

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
