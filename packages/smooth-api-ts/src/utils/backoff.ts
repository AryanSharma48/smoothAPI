import type { BackoffConfig } from "../types.js";

export function calculateBackoff(
  attempt: number,
  config: BackoffConfig,
  prevDelay?: number
): number {
  const exponential = config.baseDelay * (2 ** attempt);
  const capped = Math.min(config.maxDelay, exponential);
  const strategy = config.jitter ?? 'equal';

  switch (strategy) {
    case 'none': {
      return capped;
    }

    case 'full': {
      return Math.random() * capped;
    }

    case 'decorrelated': {
      const base = prevDelay ?? config.baseDelay;
      const upperBound = base * 3;
      const randomDelay = config.baseDelay + Math.random() * (upperBound - config.baseDelay);
      return Math.min(config.maxDelay, randomDelay);
    }

    case 'equal':
    default: {
      const half = capped / 2;
      return half + (Math.random() * half);
    }
  }
}

export function sleep(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      return reject(signal.reason || new DOMException("The operation was aborted.", "AbortError"));
    }

    let timeoutId: ReturnType<typeof setTimeout>;

    const abortHandler = () => {
      clearTimeout(timeoutId);
      reject(signal?.reason || new DOMException("The operation was aborted.", "AbortError"));
    };

    if (signal) {
      signal.addEventListener('abort', abortHandler, { once: true });
    }

    timeoutId = setTimeout(() => {
      if (signal) {
        signal.removeEventListener('abort', abortHandler);
      }
      resolve();
    }, ms);
  });
}