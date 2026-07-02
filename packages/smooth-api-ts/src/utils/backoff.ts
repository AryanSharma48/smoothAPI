import type { BackoffConfig } from "../types.js";

export function calculateBackoff( attempt: number, config: BackoffConfig ): number { 
    const exponential = config.baseDelay * ( 2**attempt);
    const capped = Math.min( config.maxDelay, exponential );
    const half = capped / 2;
    // Equal Jitter guarantees at least half the capped delay
    const jitter = half + (Math.random() * half);
    return jitter; 
}

export function sleep( ms: number): Promise<void> { 
    return new Promise(resolve => setTimeout(resolve, ms));
}