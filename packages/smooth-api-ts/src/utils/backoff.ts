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
            return reject(signal.reason || new Error("Aborted"));
        }
        
        let timeoutId: ReturnType<typeof setTimeout>;
        
        const abortHandler = () => {
            clearTimeout(timeoutId);
            reject(signal?.reason || new Error("Aborted"));
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