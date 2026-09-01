import type { BackoffConfig } from "../types.js";

export function calculateBackoff( attempt: number, config: BackoffConfig ): number { 
    const exponential = config.baseDelay * ( 2**attempt);
    const capped = Math.min( config.maxDelay, exponential );
    const half = capped / 2;
    // Equal Jitter guarantees at least half the capped delay
    const jitter = half + (Math.random() * half);
    return jitter; 
}

export function sleep(ms: number, signal?: AbortSignal | null): Promise<void> { 
    return new Promise((resolve, reject) => {
        if (signal?.aborted) {
            // Use DOMException with "AbortError" name to match native fetch behavior.
            // This ensures standard error handling (e.g. err.name === 'AbortError') works correctly.
            return reject(signal.reason || new DOMException("The operation was aborted.", "AbortError"));
        }
        
        let timeoutId: ReturnType<typeof setTimeout>;
        
        const abortHandler = () => {
            clearTimeout(timeoutId);
            // Match native fetch behavior by throwing a DOMException if no custom reason is provided.
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
