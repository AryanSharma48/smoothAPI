import type { CircuitState, CircuitBreakerConfig, CircuitEntry, CircuitStateChangeEvent  } from "./types.js";

const DEFAULTS: Required<CircuitBreakerConfig> = {
    failureThreshold: 3,
    cooldownMs: 10_000,
}

export class CircuitBreakerState {
    private readonly config: Required<CircuitBreakerConfig>;
    private readonly map: Map<string, CircuitEntry>;

    constructor(
        config: Partial<CircuitBreakerConfig> = {},
        private readonly onStateChange?: (event: CircuitStateChangeEvent) => void
    ) {
        this.config = { ...DEFAULTS, ...config};
        this.map = new Map();
    }

    private transition(domain: string, entry: CircuitEntry, to: CircuitState): void {
        const from = entry.state;
        if (from !== to) {
            entry.state = to;
            if (this.onStateChange) {
                this.onStateChange({
                    domain,
                    from,
                    to,
                    failureCount: entry.failureCount,
                });
            }
        }
    }

    private getOrCreate(domain: string): CircuitEntry {
    if (!this.map.has(domain)) {
        this.cleanup();
        this.map.set(domain, {
        state: 'CLOSED',
        failureCount: 0,
        lastFailureTime: 0,
        });
    }
    return this.map.get(domain)!; 
    }

    canRequest(domain: string): boolean {
        const entry = this.getOrCreate(domain);
        if(entry.state === "CLOSED" || entry.state === "HALF_OPEN")
            return true;
        const elapsedTime = Date.now() - entry.lastFailureTime;
        if(elapsedTime > this.config.cooldownMs){
            this.transition(domain, entry, "HALF_OPEN");
            return true;
        }
        else{
            return false;
        }         
    }

    recordSuccess(domain: string): void {
        const entry = this.getOrCreate(domain);
        entry.failureCount = 0;
        this.transition(domain, entry, "CLOSED");
    }

    recordFailure(domain: string): void {
        const entry = this.getOrCreate(domain);
        entry.failureCount++;
        if(entry.state === "HALF_OPEN"){
            this.transition(domain, entry, "OPEN");
            entry.lastFailureTime = Date.now();
            return
        }
        else if( entry.failureCount >= this.config.failureThreshold){
            this.transition(domain, entry, "OPEN");
            entry.lastFailureTime = Date.now();
        }
    }

    getState(domain: string): CircuitState {
        return this.getOrCreate(domain).state;
    }
    
    private cleanup(): void {
        // Enforce a strict domain limit to bound memory usage
        if (this.map.size <= 1000) return;
        for (const [key, entry] of this.map.entries()) {
            if (entry.state === "CLOSED" && entry.failureCount === 0) {
                this.map.delete(key);
            }
        }
    }
}

