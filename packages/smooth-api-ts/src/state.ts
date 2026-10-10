import type { CircuitState, CircuitBreakerConfig, CircuitEntry, CircuitStateChangeEvent } from "./types.js";

const DEFAULTS: Required<CircuitBreakerConfig> = {
    failureThreshold: 3,
    cooldownMs: 10_000,
};

export interface CircuitBreakerStorage {
    getState(domain: string): Promise<CircuitEntry>;
    recordFailure(domain: string, threshold: number, cooldownMs: number): Promise<CircuitState>;
    recordSuccess(domain: string): Promise<CircuitState>;
}

export class InMemoryStorage implements CircuitBreakerStorage {
    private readonly map = new Map<string, CircuitEntry>();

    private cleanup(): void {
        if (this.map.size <= 1000) return;
        for (const [key, entry] of this.map.entries()) {
            if (entry.state === "CLOSED" && entry.failureCount === 0) {
                this.map.delete(key);
            }
        }
    }

    private getOrCreate(domain: string): CircuitEntry {
        if (!this.map.has(domain)) {
            this.cleanup();
            this.map.set(domain, {
                state: "CLOSED",
                failureCount: 0,
                lastFailureTime: 0,
            });
        }
        return this.map.get(domain)!;
    }

    async getState(domain: string): Promise<CircuitEntry> {
        const entry = this.getOrCreate(domain);
        return { ...entry };
    }

    async recordFailure(domain: string, threshold: number, cooldownMs: number): Promise<CircuitState> {
        const entry = this.getOrCreate(domain);
        entry.failureCount++;
        const now = Date.now();
        if (entry.state === "HALF_OPEN" || entry.failureCount >= threshold) {
            entry.state = "OPEN";
            entry.lastFailureTime = now;
        }
        return entry.state;
    }

    async recordSuccess(domain: string): Promise<CircuitState> {
        const entry = this.getOrCreate(domain);
        entry.failureCount = 0;
        entry.state = "CLOSED";
        return "CLOSED";
    }

    // Direct synchronous access for local fast-path
    getEntrySync(domain: string): CircuitEntry {
        return this.getOrCreate(domain);
    }
}

export interface RedisClientLike {
    eval(script: string, numkeys: number, ...args: (string | number)[]): Promise<any>;
    get?(key: string): Promise<string | null>;
}

export class RedisCircuitBreakerStorage implements CircuitBreakerStorage {
    private readonly fallback: InMemoryStorage = new InMemoryStorage();
    private readonly keyPrefix: string;

    constructor(
        private readonly redis: RedisClientLike,
        keyPrefix = "smoothapi:cb:"
    ) {
        this.keyPrefix = keyPrefix;
    }

    private getKey(domain: string): string {
        return `${this.keyPrefix}${domain}`;
    }

    async getState(domain: string): Promise<CircuitEntry> {
        const key = this.getKey(domain);
        const script = `
            local state = redis.call('HGET', KEYS[1], 'state')
            local failureCount = redis.call('HGET', KEYS[1], 'failure_count')
            local lastFailureTime = redis.call('HGET', KEYS[1], 'last_failure_time')
            return {
                state or 'CLOSED',
                failureCount or '0',
                lastFailureTime or '0'
            }
        `;
        try {
            const res = (await this.redis.eval(script, 1, key)) as [string, string, string];
            return {
                state: (res[0] as CircuitState) || "CLOSED",
                failureCount: Number.parseInt(res[1] || "0", 10),
                lastFailureTime: Number.parseFloat(res[2] || "0"),
            };
        } catch {
            return this.fallback.getState(domain);
        }
    }

    async recordFailure(domain: string, threshold: number, cooldownMs: number): Promise<CircuitState> {
        const key = this.getKey(domain);
        const now = Date.now();
        const script = `
            local state = redis.call('HGET', KEYS[1], 'state') or 'CLOSED'
            local count = tonumber(redis.call('HINCRBY', KEYS[1], 'failure_count', 1))
            local now = tonumber(ARGV[1])
            local threshold = tonumber(ARGV[2])
            local cooldownMs = tonumber(ARGV[3])

            local newState = state
            if state == 'HALF_OPEN' or count >= threshold then
                newState = 'OPEN'
                redis.call('HSET', KEYS[1], 'state', 'OPEN')
                redis.call('HSET', KEYS[1], 'last_failure_time', tostring(now))
                local ttlSec = math.ceil((cooldownMs * 2) / 1000)
                if ttlSec > 0 then
                    redis.call('EXPIRE', KEYS[1], ttlSec)
                end
            end
            return newState
        `;
        try {
            const result = (await this.redis.eval(script, 1, key, now, threshold, cooldownMs)) as string;
            return result as CircuitState;
        } catch {
            return this.fallback.recordFailure(domain, threshold, cooldownMs);
        }
    }

    async recordSuccess(domain: string): Promise<CircuitState> {
        const key = this.getKey(domain);
        const script = `
            redis.call('HSET', KEYS[1], 'state', 'CLOSED')
            redis.call('HSET', KEYS[1], 'failure_count', '0')
            return 'CLOSED'
        `;
        try {
            const result = (await this.redis.eval(script, 1, key)) as string;
            return result as CircuitState;
        } catch {
            return this.fallback.recordSuccess(domain);
        }
    }
}

export class CircuitBreakerState {
    private readonly config: Required<CircuitBreakerConfig>;
    private readonly map: Map<string, CircuitEntry>;
    private readonly storage: CircuitBreakerStorage;

    constructor(
        config: Partial<CircuitBreakerConfig> = {},
        private readonly onStateChange?: (event: CircuitStateChangeEvent) => void,
        storage?: CircuitBreakerStorage
    ) {
        this.config = { ...DEFAULTS, ...config };
        this.map = new Map();
        this.storage = storage ?? new InMemoryStorage();
    }

    public getStorage(): CircuitBreakerStorage {
        return this.storage;
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
                state: "CLOSED",
                failureCount: 0,
                lastFailureTime: 0,
            });
        }
        return this.map.get(domain)!;
    }

    canRequest(domain: string): boolean {
        const entry = this.getOrCreate(domain);
        if (entry.state === "CLOSED" || entry.state === "HALF_OPEN") {
            return true;
        }
        const elapsedTime = Date.now() - entry.lastFailureTime;
        if (elapsedTime > this.config.cooldownMs) {
            this.transition(domain, entry, "HALF_OPEN");
            return true;
        }
        return false;
    }

    async canRequestAsync(domain: string): Promise<boolean> {
        const remoteEntry = await this.storage.getState(domain);
        const entry = this.getOrCreate(domain);
        entry.state = remoteEntry.state;
        entry.failureCount = remoteEntry.failureCount;
        entry.lastFailureTime = remoteEntry.lastFailureTime;

        if (entry.state === "CLOSED" || entry.state === "HALF_OPEN") {
            return true;
        }
        const elapsedTime = Date.now() - entry.lastFailureTime;
        if (elapsedTime > this.config.cooldownMs) {
            this.transition(domain, entry, "HALF_OPEN");
            return true;
        }
        return false;
    }

    recordSuccess(domain: string): void {
        const entry = this.getOrCreate(domain);
        entry.failureCount = 0;
        this.transition(domain, entry, "CLOSED");
        this.storage.recordSuccess(domain).catch(() => {});
    }

    async recordSuccessAsync(domain: string): Promise<void> {
        const entry = this.getOrCreate(domain);
        const newState = await this.storage.recordSuccess(domain);
        entry.failureCount = 0;
        this.transition(domain, entry, newState);
    }

    recordFailure(domain: string): void {
        const entry = this.getOrCreate(domain);
        entry.failureCount++;
        if (entry.state === "HALF_OPEN") {
            this.transition(domain, entry, "OPEN");
            entry.lastFailureTime = Date.now();
        } else if (entry.failureCount >= this.config.failureThreshold) {
            this.transition(domain, entry, "OPEN");
            entry.lastFailureTime = Date.now();
        }
        this.storage.recordFailure(domain, this.config.failureThreshold, this.config.cooldownMs).catch(() => {});
    }

    async recordFailureAsync(domain: string): Promise<void> {
        const entry = this.getOrCreate(domain);
        const newState = await this.storage.recordFailure(
            domain,
            this.config.failureThreshold,
            this.config.cooldownMs
        );
        entry.failureCount++;
        entry.lastFailureTime = Date.now();
        this.transition(domain, entry, newState);
    }

    getState(domain: string): CircuitState {
        return this.getOrCreate(domain).state;
    }

    async getStateAsync(domain: string): Promise<CircuitState> {
        const entry = await this.storage.getState(domain);
        const local = this.getOrCreate(domain);
        local.state = entry.state;
        local.failureCount = entry.failureCount;
        local.lastFailureTime = entry.lastFailureTime;
        return entry.state;
    }

    private cleanup(): void {
        if (this.map.size <= 1000) return;
        for (const [key, entry] of this.map.entries()) {
            if (entry.state === "CLOSED" && entry.failureCount === 0) {
                this.map.delete(key);
            }
        }
    }
}
