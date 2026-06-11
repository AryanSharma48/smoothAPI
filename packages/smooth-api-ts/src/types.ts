export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

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
