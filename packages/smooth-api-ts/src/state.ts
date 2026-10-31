import type {
  CircuitState,
  CircuitBreakerConfig,
  CircuitEntry,
  CircuitStateChangeEvent,
  PartitionBy,
  CircuitKeyFn,
} from "./types.js";

interface ResolvedCircuitBreakerConfig {
  failureThreshold: number;
  cooldownMs: number;
  successThreshold: number;
  failureRateThreshold?: number;
  windowSize: number;
  minRequestsInWindow: number;
  partitionBy: PartitionBy;
  circuitKeyFn?: CircuitKeyFn;
}

const DEFAULTS: ResolvedCircuitBreakerConfig = {
  failureThreshold: 3,
  cooldownMs: 10_000,
  successThreshold: 1,
  failureRateThreshold: undefined,
  windowSize: 20,
  minRequestsInWindow: 5,
  partitionBy: 'host',
};

export class CircuitBreakerState {
  private readonly config: ResolvedCircuitBreakerConfig;
  private readonly map: Map<string, CircuitEntry>;

  constructor(
    config: Partial<CircuitBreakerConfig> = {},
    private readonly onStateChange?: (event: CircuitStateChangeEvent) => void
  ) {
    this.config = { ...DEFAULTS, ...config };
    this.map = new Map();
  }

  private transition(
    domain: string,
    entry: CircuitEntry,
    to: CircuitState,
    failureRate?: number
  ): void {
    const from = entry.state;
    if (from !== to) {
      entry.state = to;
      if (this.onStateChange) {
        const event: CircuitStateChangeEvent = {
          domain,
          from,
          to,
          failureCount: entry.failureCount,
        };
        if (failureRate !== undefined) {
          event.failureRate = failureRate;
        }
        this.onStateChange(event);
      }
    }
  }

  private recordWindowOutcome(entry: CircuitEntry, success: boolean): void {
    const size = entry.window.length;
    const isFailure = success ? 0 : 1;
    if (entry.windowCount < size) {
      entry.window[entry.windowIndex] = isFailure;
      if (isFailure === 1) entry.windowFailures++;
      entry.windowCount++;
    } else {
      const prev = entry.window[entry.windowIndex];
      if (prev === 1 && isFailure === 0) entry.windowFailures--;
      else if (prev === 0 && isFailure === 1) entry.windowFailures++;
      entry.window[entry.windowIndex] = isFailure;
    }
    entry.windowIndex = (entry.windowIndex + 1) % size;
  }

  private resetWindow(entry: CircuitEntry): void {
    entry.window.fill(0);
    entry.windowIndex = 0;
    entry.windowCount = 0;
    entry.windowFailures = 0;
  }

  private getOrCreate(domain: string): CircuitEntry {
    if (!this.map.has(domain)) {
      this.cleanup();
      const size = Math.max(1, this.config.windowSize || 20);
      this.map.set(domain, {
        state: 'CLOSED',
        failureCount: 0,
        lastFailureTime: 0,
        consecutiveSuccesses: 0,
        probeInFlight: false,
        window: new Uint8Array(size),
        windowIndex: 0,
        windowCount: 0,
        windowFailures: 0,
      });
    }
    return this.map.get(domain)!;
  }

  canRequest(domain: string): boolean {
    const entry = this.getOrCreate(domain);
    if (entry.state === 'CLOSED') {
      return true;
    }

    const elapsedTime = Date.now() - entry.lastFailureTime;
    if (entry.state === 'OPEN') {
      if (elapsedTime > this.config.cooldownMs) {
        this.transition(domain, entry, 'HALF_OPEN');
        entry.consecutiveSuccesses = 0;
        entry.probeInFlight = true;
        return true;
      }
      return false;
    }

    // State is HALF_OPEN: only allow single in-flight probe
    if (entry.probeInFlight) {
      return false;
    }
    entry.probeInFlight = true;
    return true;
  }

  releaseProbe(domain: string): void {
    const entry = this.map.get(domain);
    if (entry && entry.state === 'HALF_OPEN') {
      entry.probeInFlight = false;
    }
  }

  recordSuccess(domain: string): void {
    const entry = this.getOrCreate(domain);
    entry.probeInFlight = false;
    this.recordWindowOutcome(entry, true);

    if (entry.state === 'HALF_OPEN') {
      entry.consecutiveSuccesses++;
      if (entry.consecutiveSuccesses >= this.config.successThreshold) {
        entry.failureCount = 0;
        entry.consecutiveSuccesses = 0;
        this.resetWindow(entry);
        this.transition(domain, entry, 'CLOSED');
      }
    } else if (entry.state === 'CLOSED') {
      entry.failureCount = 0;
    }
  }

  recordFailure(domain: string): void {
    const entry = this.getOrCreate(domain);
    entry.probeInFlight = false;
    this.recordWindowOutcome(entry, false);
    entry.failureCount++;

    if (entry.state === 'HALF_OPEN') {
      entry.consecutiveSuccesses = 0;
      entry.lastFailureTime = Date.now();
      this.transition(domain, entry, 'OPEN');
      return;
    }

    const consecutiveTrip = entry.failureCount >= this.config.failureThreshold;
    let rateTrip = false;
    let failureRate: number | undefined;

    if (
      this.config.failureRateThreshold !== undefined &&
      entry.windowCount >= this.config.minRequestsInWindow
    ) {
      failureRate = entry.windowFailures / entry.windowCount;
      if (failureRate >= this.config.failureRateThreshold) {
        rateTrip = true;
      }
    }

    if (consecutiveTrip || rateTrip) {
      entry.lastFailureTime = Date.now();
      this.transition(domain, entry, 'OPEN', failureRate);
    }
  }

  getState(domain: string): CircuitState {
    const entry = this.getOrCreate(domain);
    if (
      entry.state === 'OPEN' &&
      Date.now() - entry.lastFailureTime > this.config.cooldownMs
    ) {
      return 'HALF_OPEN';
    }
    return entry.state;
  }

  getStats(domain: string) {
    const entry = this.getOrCreate(domain);
    return {
      state: this.getState(domain),
      failureCount: entry.failureCount,
      consecutiveSuccesses: entry.consecutiveSuccesses,
      windowCount: entry.windowCount,
      windowFailures: entry.windowFailures,
      failureRate: entry.windowCount > 0 ? entry.windowFailures / entry.windowCount : 0,
    };
  }

  private cleanup(): void {
    // Enforce a strict domain limit to bound memory usage
    if (this.map.size <= 1000) return;
    for (const [key, entry] of this.map.entries()) {
      if (entry.state === 'CLOSED' && entry.failureCount === 0 && entry.windowFailures === 0) {
        this.map.delete(key);
      }
    }
  }
}
