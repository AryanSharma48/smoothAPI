import { CircuitBreakerState } from "./state.js";
import { calculateBackoff, sleep } from "./utils/backoff.js";
import { CircuitOpenError, ResilientFetchConfig } from "./types.js";

const BACKOFF_DEFAULTS = {
  baseDelay: 100,
  maxDelay: 30_000,
  maxRetries: 3,
};

const DEFAULT_RETRY_ON = [429, 500, 502, 503, 504];

export function createResilientFetch<T>(globalConfig: ResilientFetchConfig<T>) {
  const backoffConfig = { ...BACKOFF_DEFAULTS, ...globalConfig.backoff };
  const retryOn = globalConfig.retryOn ?? DEFAULT_RETRY_ON;
  const breaker = new CircuitBreakerState(globalConfig.circuitBreaker);

  return async function resilientFetch(
    url: string | URL,
    options?: RequestInit
  ): Promise<Response | T> {
    const domain = new URL(url).hostname;

    // Block before any network IO if the circuit is OPEN.
    if (!breaker.canRequest(domain)) {
      if (globalConfig.fallback !== undefined) {
        return globalConfig.fallback as T;
      }
      throw new CircuitOpenError(domain);
    }

    let lastError: unknown;

    for (let attempt = 0; attempt <= backoffConfig.maxRetries; attempt++) {
      try {
        const response = await fetch(url, options);

        // fetch() resolves for any HTTP status. Retryable codes need to be
        // treated as failures manually so they dont throw on their own.
        if (retryOn.includes(response.status)) {
          breaker.recordFailure(domain);
          throw new Error(`HTTP ${response.status}`);
        }

        breaker.recordSuccess(domain);
        return response;
      } catch (err) {
        lastError = err;
        breaker.recordFailure(domain);

        // Don't sleep after the final attempt
        if (attempt < backoffConfig.maxRetries) {
          await sleep(calculateBackoff(attempt, backoffConfig));
        }
      }
    }

    throw lastError;
  };
}
