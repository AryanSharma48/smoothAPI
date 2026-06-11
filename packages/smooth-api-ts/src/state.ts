import type { CircuitState, CircuitBreakerConfig, CircuitEntry  } from "./types.js";

const DEFAULTS: Required<CircuitBreakerConfig> = {
    failureThreshold: 3,
    cooldownMs: 10_000,
}

export class CircuitBreakerState {
    private readonly config: Required<CircuitBreakerConfig>;
    private readonly map: Map<string, CircuitEntry>;

    constructor(config: Partial<CircuitBreakerConfig> = {}) {
        this.config = { ...DEFAULTS, ...config};
        this.map = new Map();
    }

    private getOrCreate(domain: string): CircuitEntry {
    if (!this.map.has(domain)) {
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
            entry.state = "HALF_OPEN";
            return true;
        }
        else{
            return false;
        }         
    }

    recordSuccess(domain: string): void {
        const entry = this.getOrCreate(domain);
        entry.state = "CLOSED";
        entry.failureCount = 0;
    }

    recordFailure(domain: string): void {
        const entry = this.getOrCreate(domain);
        entry.failureCount++;
        if(entry.state === "HALF_OPEN"){
            entry.state = "OPEN";
            entry.lastFailureTime = Date.now();
            return
        }
        else if( entry.failureCount >= this.config.failureThreshold){
            entry.state = "OPEN";
            entry.lastFailureTime = Date.now();
        }
    }

    getState(domain: string): CircuitState {
        return this.getOrCreate(domain).state;
    }
    

}

