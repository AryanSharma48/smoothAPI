import { CircuitBreakerState } from "./state.js";
import { calculateBackoff, sleep } from "./utils/backoff.js";
import { CircuitOpenError, ResilientFetchConfig } from "./types.js";
import { RequestDeduplicator } from "./dedup.js";

const BACKOFF_DEFAULTS = {
  baseDelay: 100,
  maxDelay: 30_000,
  maxRetries: 3,
};

const DEFAULT_RETRY_ON = [429, 500, 502, 503, 504];

export function createSmoothFetch<T>(globalConfig: ResilientFetchConfig<T>) {
  const backoffConfig = { ...BACKOFF_DEFAULTS, ...globalConfig.backoff };
  const retryOn = globalConfig.retryOn ?? DEFAULT_RETRY_ON;
  const breaker = new CircuitBreakerState(globalConfig.circuitBreaker);
  const deduplicator = globalConfig.deduplication
    ? new RequestDeduplicator(globalConfig.deduplication.keyFn)
    : null;

  return async function smoothFetch(
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

    // The core fetch-with-retry logic extracted into a thunk so the
    // deduplicator can decide whether to run it or share an existing Promise.
    const executeRequest = (): Promise<Response | T> => {
      let lastError: unknown;

      const run = async (): Promise<Response | T> => {
        for (let attempt = 0; attempt <= backoffConfig.maxRetries; attempt++) {
          try {
            const response = await fetch(url, options);

            // fetch() resolves for any HTTP status. Retryable codes need to be
            // treated as failures manually.
            if (retryOn.includes(response.status)) {
              breaker.recordFailure(domain);
              if (attempt < backoffConfig.maxRetries) {
                await sleep(calculateBackoff(attempt, backoffConfig));
                continue;
              }
              return response;
            }

            if (response.status >= 400 && globalConfig.fallbackOnNonRetryable) {
              const message = `Non-retryable HTTP error: ${response.status}${response.statusText ? ' ' + response.statusText : ''}`;
              if (globalConfig.onNonRetryableError) {
                globalConfig.onNonRetryableError(response.status, message);
              } else if (typeof window !== 'undefined') {
                window.alert(message);
              } else {
                console.error(message);
              }

              breaker.recordSuccess(domain);

              if (globalConfig.fallback !== undefined) {
                return globalConfig.fallback as T;
              }

              return new Response(
                JSON.stringify({
                  error: true,
                  status: response.status,
                  message,
                }),
                {
                  status: response.status,
                  statusText: response.statusText,
                  headers: { "Content-Type": "application/json" }
                }
              );
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

      return run();
    };

    if (deduplicator) {
      return deduplicator.execute(url, options, executeRequest);
    }

    return executeRequest();
  };
}

/** @deprecated use createSmoothFetch instead */
export const createResilientFetch = createSmoothFetch;
