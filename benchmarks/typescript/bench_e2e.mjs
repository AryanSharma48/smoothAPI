/**
 * End-to-End API Client Benchmark Runner (TypeScript Native vs TypeScript + Node-API).
 *
 * Scenarios:
 *   1. normal_200            : 200 OK baseline request overhead
 *   2. intermittent_503_429  : 1st attempt fails (503/429 with Retry-After: 0), 2nd succeeds (200)
 *   3. repeated_failures_cb  : Persistent 503 trips circuit breaker after 3 failures; remaining
 *                              requests fast-fail in-process via OPEN circuit fallback
 */

import { createSmoothFetch, CircuitOpenError } from '../../packages/smooth-api-ts/dist/index.js';
import { sleep } from '../../packages/smooth-api-ts/dist/utils/backoff.js';
import { createRequire } from 'node:module';
import { performance } from 'node:perf_hooks';

const require = createRequire(import.meta.url);
const native = require('../../bindings/node');

function getCircuitKey(url, parsedUrl, options, cbConfig) {
  if (cbConfig?.circuitKeyFn) {
    return cbConfig.circuitKeyFn(url, options);
  }
  if (cbConfig?.partitionBy === 'host-and-path') {
    return `${parsedUrl.hostname}${parsedUrl.pathname}`;
  }
  return parsedUrl.hostname;
}

class NapiCircuitBreakerState {
  constructor(config = {}) {
    this.failureThreshold = config.failureThreshold ?? 3;
    this.cooldownMs = config.cooldownMs ?? 10000;
    this.map = new Map();
  }

  getOrCreate(domain) {
    if (!this.map.has(domain)) {
      if (this.map.size > 1000) {
        for (const [k, b] of this.map.entries()) {
          if (b.getState() === 'CLOSED') this.map.delete(k);
        }
      }
      this.map.set(
        domain,
        new native.NativeCircuitBreaker(this.failureThreshold, this.cooldownMs),
      );
    }
    return this.map.get(domain);
  }

  canRequest(domain) {
    const breaker = this.getOrCreate(domain);
    return breaker.canRequest(Date.now());
  }

  recordSuccess(domain) {
    const breaker = this.getOrCreate(domain);
    breaker.recordSuccess();
  }

  recordFailure(domain) {
    const breaker = this.getOrCreate(domain);
    breaker.recordFailure(Date.now());
  }

  releaseProbe(domain) {
    const breaker = this.map.get(domain);
    if (breaker) breaker.releaseProbe();
  }
}

function createFairNapiSmoothFetch(globalConfig) {
  const baseDelay = globalConfig.backoff?.baseDelay ?? 100;
  const maxDelay = globalConfig.backoff?.maxDelay ?? 30000;
  const maxRetries = globalConfig.backoff?.maxRetries ?? 3;
  const jitter = globalConfig.backoff?.jitter ?? 'none';
  const breaker = new NapiCircuitBreakerState(globalConfig.circuitBreaker);

  return async function fairNapiSmoothFetch(url, options) {
    const startTime = Date.now();
    const urlStr = url.toString();
    const origin =
      typeof window !== 'undefined' && window.location
        ? window.location.origin
        : 'http://localhost';
    const parsedUrl = new URL(urlStr, origin);
    const domain = parsedUrl.hostname;
    const circuitKey = getCircuitKey(url, parsedUrl, options, globalConfig.circuitBreaker);

    if (!breaker.canRequest(circuitKey)) {
      if (globalConfig.onFailure) {
        globalConfig.onFailure({
          url: urlStr,
          domain,
          attempts: 0,
          durationMs: Date.now() - startTime,
          error: new CircuitOpenError(circuitKey),
          isCircuitOpen: true,
        });
      }
      if (globalConfig.fallback !== undefined) {
        return globalConfig.fallback;
      }
      throw new CircuitOpenError(circuitKey);
    }

    let prevDelay = null;
    try {
      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        const response = await fetch(url, options);
        const retryAfter = response.status === 429 ? response.headers.get('Retry-After') : null;
        const decision = native.evaluateResponseNative(
          response.status,
          attempt,
          baseDelay,
          maxDelay,
          maxRetries,
          retryAfter,
        );

        if (decision.type === 'Success' || decision.type === 'Terminal') {
          breaker.recordSuccess(circuitKey);
          return response;
        }

        breaker.recordFailure(circuitKey);

        if (decision.type === 'Retry') {
          let delayMs = decision.delayMs ?? 0;
          if (jitter !== 'none' && !(response.status === 429 && retryAfter !== null)) {
            delayMs = native.calculateBackoffNative(
              attempt,
              baseDelay,
              maxDelay,
              jitter,
              prevDelay,
              Math.random(),
            );
          }
          prevDelay = delayMs;
          await sleep(delayMs, options?.signal);
          continue;
        }

        return response;
      }
    } finally {
      breaker.releaseProbe(circuitKey);
    }
  };
}

function createNapiSmoothFetch(config) {
  const baseDelay = config.backoff?.baseDelay ?? 1;
  const maxDelay = config.backoff?.maxDelay ?? 30000;
  const maxRetries = config.backoff?.maxRetries ?? 3;
  const jitter = config.backoff?.jitter ?? 'none';
  const threshold = config.circuitBreaker?.failureThreshold ?? 3;
  const cooldownMs = config.circuitBreaker?.cooldownMs ?? 60000;
  const fallback = config.fallback;

  const breaker = new native.NativeCircuitBreaker(threshold, cooldownMs);

  return async function napiSmoothFetch(url, options) {
    const now = Date.now();
    if (!breaker.canRequest(now)) {
      if (fallback !== undefined) return fallback;
      throw new Error('CircuitOpenError');
    }

    let prevDelay = null;
    try {
      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        const response = await fetch(url, options);
        const retryAfter = response.status === 429 ? response.headers.get('Retry-After') : null;
        const decision = native.evaluateResponseNative(
          response.status,
          attempt,
          baseDelay,
          maxDelay,
          maxRetries,
          retryAfter,
        );

        if (decision.type === 'Success') {
          breaker.recordSuccess();
          return response;
        }

        if (decision.type === 'Terminal') {
          breaker.recordSuccess();
          return response;
        }

        breaker.recordFailure(Date.now());

        if (decision.type === 'Retry') {
          let delayMs = decision.delayMs ?? 0;
          if (jitter !== 'none' && !(response.status === 429 && retryAfter !== null)) {
            delayMs = native.calculateBackoffNative(
              attempt,
              baseDelay,
              maxDelay,
              jitter,
              prevDelay,
              Math.random(),
            );
          }
          prevDelay = delayMs;
          await sleep(delayMs);
          continue;
        }

        return response;
      }
    } finally {
      breaker.releaseProbe();
    }
  };
}

function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[idx];
}

async function runScenario({ impl, scenario, baseUrl, requests, warmup, round, fair }) {
  const makeClient =
    impl === 'ts_napi'
      ? fair
        ? createFairNapiSmoothFetch
        : createNapiSmoothFetch
      : createSmoothFetch;

  let clientConfig;
  if (scenario === 'normal_200') {
    clientConfig = {
      backoff: { baseDelay: 1, maxDelay: 100, maxRetries: 2, jitter: 'none' },
      circuitBreaker: { failureThreshold: 1000000, cooldownMs: 60000 },
    };
  } else if (scenario === 'intermittent_503_429') {
    clientConfig = {
      backoff: { baseDelay: 1, maxDelay: 100, maxRetries: 2, jitter: 'none' },
      circuitBreaker: { failureThreshold: 1000000, cooldownMs: 60000 },
    };
  } else if (scenario === 'repeated_failures_cb') {
    clientConfig = {
      backoff: { baseDelay: 1, maxDelay: 100, maxRetries: 0, jitter: 'none' },
      circuitBreaker: { failureThreshold: 3, cooldownMs: 600000 },
      fallback: { fallback: true },
    };
  } else {
    throw new Error(`Unknown scenario: ${scenario}`);
  }

  // Warm-up phase with a separate client instance
  const warmupClient = makeClient(clientConfig);
  for (let i = 0; i < warmup; i++) {
    const res = await warmupClient(`${baseUrl}/${scenario}?id=w_${i}`);
    if (res && typeof res.text === 'function') await res.text();
  }

  // Timed phase with a fresh client instance
  const client = makeClient(clientConfig);
  const latenciesMs = new Array(requests);

  const memBefore = process.memoryUsage();
  const cpuStart = process.cpuUsage();
  const wallStart = performance.now();

  for (let i = 0; i < requests; i++) {
    const t0 = performance.now();
    const res = await client(`${baseUrl}/${scenario}?id=${round}_${i}`);
    if (res && typeof res.text === 'function') await res.text();
    const t1 = performance.now();
    latenciesMs[i] = t1 - t0;
  }

  const wallEnd = performance.now();
  const cpuDiff = process.cpuUsage(cpuStart);
  const memAfter = process.memoryUsage();

  const elapsedMs = wallEnd - wallStart;
  const reqPerSec = requests / (elapsedMs / 1000.0);
  const cpuTotalMs = (cpuDiff.user + cpuDiff.system) / 1000.0;
  const cpuPct = (cpuTotalMs / elapsedMs) * 100.0;
  const cpuMsPer1k = (cpuTotalMs / requests) * 1000.0;
  const rssMb = Math.max(memBefore.rss, memAfter.rss) / (1024 * 1024);
  const heapUsedMb = memAfter.heapUsed / (1024 * 1024);

  const sorted = [...latenciesMs].sort((a, b) => a - b);
  const meanMs = sorted.reduce((a, b) => a + b, 0) / sorted.length;

  return {
    scenario,
    impl,
    round,
    requests,
    elapsed_ms: Number(elapsedMs.toFixed(4)),
    req_per_sec: Number(reqPerSec.toFixed(2)),
    mean_ms: Number(meanMs.toFixed(4)),
    p50_ms: Number(percentile(sorted, 50).toFixed(4)),
    p95_ms: Number(percentile(sorted, 95).toFixed(4)),
    p99_ms: Number(percentile(sorted, 99).toFixed(4)),
    cpu_ms: Number(cpuTotalMs.toFixed(4)),
    cpu_ms_per_1k_reqs: Number(cpuMsPer1k.toFixed(4)),
    cpu_pct: Number(cpuPct.toFixed(2)),
    rss_mb: Number(rssMb.toFixed(2)),
    heap_mb: Number(heapUsedMb.toFixed(2)),
  };
}

function parseArgs() {
  const args = process.argv.slice(2);
  let impl = 'ts_native';
  let scenario = 'normal_200';
  let baseUrl = 'http://127.0.0.1:3099';
  let requests = 500;
  let warmup = 50;
  let round = 1;
  let fair = false;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--impl') impl = args[++i];
    else if (args[i] === '--scenario') scenario = args[++i];
    else if (args[i] === '--url') baseUrl = args[++i];
    else if (args[i] === '--requests') requests = parseInt(args[++i], 10);
    else if (args[i] === '--warmup') warmup = parseInt(args[++i], 10);
    else if (args[i] === '--round') round = parseInt(args[++i], 10);
    else if (args[i] === '--fair') fair = true;
  }
  return { impl, scenario, baseUrl, requests, warmup, round, fair };
}

const opts = parseArgs();
runScenario(opts)
  .then((res) => console.log(JSON.stringify(res)))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
