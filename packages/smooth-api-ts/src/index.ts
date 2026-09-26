import { CircuitBreakerState } from "./state.js";
import { calculateBackoff, sleep } from "./utils/backoff.js";
import { CircuitOpenError, SmoothFetchConfig, ShouldRetryPredicate } from "./types.js";
import { RequestDeduplicator } from "./dedup.js";

export * from "./types.js";
export type { ShouldRetryPredicate } from "./types.js";

const BACKOFF_DEFAULTS = {
  baseDelay: 100,
  maxDelay: 30_000,
  maxRetries: 3,
};

const DEFAULT_RETRY_ON = [429, 500, 502, 503, 504];

function safeInvoke<T>(fn: ((arg: T) => void | Promise<void>) | undefined, arg: T): void {
  if (!fn) return;
  try {
    const result = fn(arg);
    if (result && typeof (result as any).catch === 'function') {
      (result as any).catch((err: unknown) => {
        console.error('[smoothAPI] Error in lifecycle hook:', err);
      });
    }
  } catch (err) {
    console.error('[smoothAPI] Error in lifecycle hook:', err);
  }
}

async function evaluateShouldRetry(
  predicate: ShouldRetryPredicate | undefined,
  response?: Response,
  error?: unknown,
  fallback: boolean = false
): Promise<boolean> {
  if (!predicate) return fallback;
  try {
    let clonedResponse: Response | undefined;
    if (response) {
      try {
        clonedResponse = typeof response.clone === 'function' ? response.clone() : response;
      } catch {
        clonedResponse = response;
      }
    }
    const result = await predicate(clonedResponse, error);
    return Boolean(result);
  } catch (err) {
    console.error('[smoothAPI] Error in shouldRetry predicate:', err);
    return fallback;
  }
}

export function createSmoothFetch<T>(globalConfig: SmoothFetchConfig<T>) {
  const backoffConfig = { ...BACKOFF_DEFAULTS, ...globalConfig.backoff };
  const retryOn = globalConfig.retryOn ?? DEFAULT_RETRY_ON;
  const breaker = new CircuitBreakerState(
    globalConfig.circuitBreaker,
    globalConfig.onCircuitStateChange 
      ? (event) => safeInvoke(globalConfig.onCircuitStateChange, event)
      : undefined
  );
  const deduplicator = globalConfig.deduplication
    ? new RequestDeduplicator(globalConfig.deduplication.keyFn)
    : null;

  return async function smoothFetch(
    url: string | URL,
    options?: RequestInit
  ): Promise<Response | T> {
    const startTime = Date.now();
    const urlStr = url.toString();
    // Fallback to local origin to support relative paths
    const domain = new URL(urlStr, typeof window !== 'undefined' && window.location ? window.location.origin : 'http://localhost').hostname;

    // Block before any network IO if the circuit is OPEN.
    if (!breaker.canRequest(domain)) {
      if (globalConfig.onFailure) {
        safeInvoke(globalConfig.onFailure, {
          url: urlStr,
          domain,
          attempts: 0,
          durationMs: Date.now() - startTime,
          error: new CircuitOpenError(domain),
          isCircuitOpen: true,
        });
      }
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
        let prevDelay: number | undefined;
        let attemptCount = 0;
        for (let attempt = 0; attempt <= backoffConfig.maxRetries; attempt++) {
          attemptCount = attempt + 1;
          // Pre-flight abort check
          if (options?.signal?.aborted) {
            const abortErr = options.signal.reason || new DOMException("The operation was aborted.", "AbortError");
            if (globalConfig.onFailure) {
              safeInvoke(globalConfig.onFailure, {
                url: urlStr,
                domain,
                attempts: attemptCount - 1,
                durationMs: Date.now() - startTime,
                error: abortErr,
                isCircuitOpen: false,
              });
            }
            throw abortErr;
          }

          let timeoutId: ReturnType<typeof setTimeout> | undefined;
          let currentOptions = options;
          let controller: AbortController | undefined;
          let abortListener: (() => void) | undefined;

          if (
            typeof globalConfig.timeoutMs === 'number' &&
            Number.isFinite(globalConfig.timeoutMs) &&
            globalConfig.timeoutMs > 0
          ) {
            controller = new AbortController();
            if (options?.signal) {
              const userSignal = options.signal;
              abortListener = () => controller?.abort(userSignal.reason);
              userSignal.addEventListener('abort', abortListener);
              if (userSignal.aborted) {
                controller.abort(userSignal.reason);
              }
            }
            currentOptions = { ...options, signal: controller.signal };
            timeoutId = setTimeout(() => controller?.abort(new Error('Request Timeout')), globalConfig.timeoutMs);
          }

          try {
            const response = await fetch(url, currentOptions);

            const defaultRetryable = retryOn.includes(response.status);
            const isRetryable = globalConfig.shouldRetry
              ? await evaluateShouldRetry(globalConfig.shouldRetry, response, undefined, defaultRetryable)
              : defaultRetryable;

            // fetch() resolves for any HTTP status. Retryable codes or custom predicates need to be
            // treated as failures manually.
            if (isRetryable) {
              breaker.recordFailure(domain);

              if (attempt < backoffConfig.maxRetries) {
                let delayMs = calculateBackoff(attempt, backoffConfig, prevDelay);
                if (response.status === 429) {
                  const retryAfter = response.headers.get('Retry-After');
                  if (retryAfter) {
                    const parsed = parseInt(retryAfter, 10);
                    if (!Number.isNaN(parsed) && parsed > 0) {
                      delayMs = parsed * 1000;
                    }
                  }
                }
                prevDelay = delayMs;

                if (globalConfig.onRetry) {
                  safeInvoke(globalConfig.onRetry, {
                    attempt: attempt + 1,
                    maxRetries: backoffConfig.maxRetries,
                    delayMs,
                    status: response.status,
                    url: urlStr,
                    domain,
                  });
                }

                await sleep(delayMs, options?.signal);
                continue;
              }

              if (globalConfig.onFailure) {
                safeInvoke(globalConfig.onFailure, {
                  url: urlStr,
                  domain,
                  attempts: attemptCount,
                  durationMs: Date.now() - startTime,
                  status: response.status,
                  response,
                  error: new Error(`HTTP ${response.status}: Retries exhausted`),
                  isCircuitOpen: false,
                });
              }
              return response;
            }

            if (response.status >= 400 && globalConfig.fallbackOnNonRetryable) {
              const message = `Non-retryable HTTP error: ${response.status}${response.statusText ? ' ' + response.statusText : ''}`;
              if (globalConfig.onNonRetryableError) {
                globalConfig.onNonRetryableError(response.status, message);
              } else {
                console.error(message);
              }

              breaker.recordSuccess(domain);

              if (globalConfig.onFailure) {
                safeInvoke(globalConfig.onFailure, {
                  url: urlStr,
                  domain,
                  attempts: attemptCount,
                  durationMs: Date.now() - startTime,
                  status: response.status,
                  response,
                  error: new Error(message),
                  isCircuitOpen: false,
                });
              }

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

            if (response.status >= 400) {
              if (globalConfig.onFailure) {
                safeInvoke(globalConfig.onFailure, {
                  url: urlStr,
                  domain,
                  attempts: attemptCount,
                  durationMs: Date.now() - startTime,
                  status: response.status,
                  response,
                  error: new Error(`HTTP ${response.status}${response.statusText ? ' ' + response.statusText : ''}`),
                  isCircuitOpen: false,
                });
              }
            } else {
              if (globalConfig.onSuccess) {
                safeInvoke(globalConfig.onSuccess, {
                  url: urlStr,
                  domain,
                  attempts: attemptCount,
                  durationMs: Date.now() - startTime,
                  status: response.status,
                  response,
                });
              }
            }

            return response;
          } catch (err: any) {
            lastError = err;
            // If it's an AbortError but not from our internal timeout, don't retry.
            // (We know it's our timeout if controller is aborted and the user's signal isn't).
            const isInternalTimeout = controller?.signal?.aborted && !options?.signal?.aborted;
            if (err?.name === 'AbortError' && !isInternalTimeout) {
              if (globalConfig.onFailure) {
                safeInvoke(globalConfig.onFailure, {
                  url: urlStr,
                  domain,
                  attempts: attemptCount,
                  durationMs: Date.now() - startTime,
                  error: err,
                  isCircuitOpen: false,
                });
              }
              throw err;
            }

            // Do not retry or record failure if the user explicitly aborted the request
            if (options?.signal?.aborted) {
              if (globalConfig.onFailure) {
                safeInvoke(globalConfig.onFailure, {
                  url: urlStr,
                  domain,
                  attempts: attemptCount,
                  durationMs: Date.now() - startTime,
                  error: err,
                  isCircuitOpen: false,
                });
              }
              throw err;
            }

            if (globalConfig.shouldRetry) {
              const should = await evaluateShouldRetry(globalConfig.shouldRetry, undefined, err, true);
              if (!should) {
                breaker.recordFailure(domain);
                if (globalConfig.onFailure) {
                  safeInvoke(globalConfig.onFailure, {
                    url: urlStr,
                    domain,
                    attempts: attemptCount,
                    durationMs: Date.now() - startTime,
                    error: err,
                    isCircuitOpen: false,
                  });
                }
                throw err;
              }
            }

            breaker.recordFailure(domain);

            // Don't sleep after the final attempt
            if (attempt < backoffConfig.maxRetries) {
              const delayMs = calculateBackoff(attempt, backoffConfig, prevDelay);
              prevDelay = delayMs;
              if (globalConfig.onRetry) {
                safeInvoke(globalConfig.onRetry, {
                  attempt: attempt + 1,
                  maxRetries: backoffConfig.maxRetries,
                  delayMs,
                  error: err instanceof Error ? err : new Error(String(err)),
                  url: urlStr,
                  domain,
                });
              }
              await sleep(delayMs, options?.signal);
            }
          } finally {
            if (timeoutId) clearTimeout(timeoutId);
            if (abortListener && options?.signal) {
              options.signal.removeEventListener('abort', abortListener);
            }
          }
        }

        if (globalConfig.onFailure) {
          safeInvoke(globalConfig.onFailure, {
            url: urlStr,
            domain,
            attempts: attemptCount,
            durationMs: Date.now() - startTime,
            error: lastError,
            isCircuitOpen: false,
          });
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
export const createResilientFetch = (...args: Parameters<typeof createSmoothFetch>) => {
  if (typeof console !== "undefined" && console.warn) {
    console.warn(
      "[smoothAPI] createResilientFetch is deprecated; use createSmoothFetch instead.",
    );
  }
  return createSmoothFetch(...args);
};
