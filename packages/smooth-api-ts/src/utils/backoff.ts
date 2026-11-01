import type { BackoffConfig } from "../types.js";

function computeCappedDelay(baseDelay: number, maxDelay: number, attempt: number): number {
  if (baseDelay <= 0 || maxDelay <= 0) {
    return 0;
  }
  if (baseDelay >= maxDelay) {
    return maxDelay;
  }
  let remaining = Math.max(0, Math.trunc(attempt));
  let current = baseDelay;
  while (remaining > 0 && current < maxDelay) {
    const step = Math.min(remaining, 52);
    current *= 2 ** step;
    remaining -= step;
  }
  return Math.min(maxDelay, current);
}

export function calculateBackoff(
  attempt: number,
  config: BackoffConfig,
  prevDelay?: number,
  randomFactor: number = Math.random()
): number {
  const baseDelay = Math.max(0, config.baseDelay);
  const maxDelay = Math.max(0, config.maxDelay);
  const capped = computeCappedDelay(baseDelay, maxDelay, attempt);
  if (capped === 0) {
    return 0;
  }
  const factor = Math.min(1, Math.max(0, randomFactor));
  const strategy = config.jitter ?? 'equal';

  switch (strategy) {
    case 'none': {
      return capped;
    }

    case 'full': {
      return factor * capped;
    }

    case 'decorrelated': {
      const base = prevDelay ?? baseDelay;
      const upperBound = Math.max(baseDelay, base * 3);
      const randomDelay = baseDelay + factor * (upperBound - baseDelay);
      return Math.min(maxDelay, randomDelay);
    }

    case 'equal':
    default: {
      const half = capped / 2;
      return half + (factor * half);
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
