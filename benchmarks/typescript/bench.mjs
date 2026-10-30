import { calculateBackoff } from '../../packages/smooth-api-ts/dist/utils/backoff.js';
import { CircuitBreakerState } from '../../packages/smooth-api-ts/dist/state.js';
import { createRequire } from 'node:module';
import { performance } from 'node:perf_hooks';

const require = createRequire(import.meta.url);
const native = require('../../bindings/node');

const DEFAULT_RETRY_ON = [429, 500, 502, 503, 504];

function evaluateResponse(status, attempt, config, retryAfterHeader) {
  if (status >= 200 && status < 400) {
    return { type: 'Success' };
  }
  if (!DEFAULT_RETRY_ON.includes(status)) {
    return { type: 'Terminal' };
  }
  if (attempt >= config.maxRetries) {
    return { type: 'Exhausted' };
  }
  let delayMs = calculateBackoff(attempt, config);
  if (status === 429 && retryAfterHeader) {
    const trimmed = retryAfterHeader.trim();
    if (/^\d+$/.test(trimmed)) {
      const parsed = Number(trimmed);
      if (Number.isSafeInteger(parsed) && parsed >= 0) {
        delayMs = parsed * 1000;
      }
    }
  }
  return { type: 'Retry', delayMs };
}

function verifyCorrectness(config, impl) {
  const expectedBackoffs = [
    [0, 100],
    [1, 200],
    [2, 400],
    [3, 800],
    [10, 30000],
  ];

  for (const [attempt, expected] of expectedBackoffs) {
    const delay = impl === 'ts_napi'
      ? native.calculateBackoffNative(attempt, config.baseDelay, config.maxDelay)
      : calculateBackoff(attempt, config);
    if (delay !== expected) {
      throw new Error(`${impl} correctness failed: attempt ${attempt} returned ${delay}, expected ${expected}`);
    }
  }

  const evalFn = (status, attempt, header) =>
    impl === 'ts_napi'
      ? native.evaluateResponseNative(status, attempt, config.baseDelay, config.maxDelay, config.maxRetries, header)
      : evaluateResponse(status, attempt, config, header);

  const d1 = evalFn(200, 0, null);
  if (d1.type !== 'Success') throw new Error(`${impl} correctness failed on 200`);

  const d2 = evalFn(404, 0, null);
  if (d2.type !== 'Terminal') throw new Error(`${impl} correctness failed on 404`);

  const d3 = evalFn(503, 0, null);
  if (d3.type !== 'Retry' || d3.delayMs !== 100) throw new Error(`${impl} correctness failed on 503`);

  const d4 = evalFn(429, 0, '5');
  if (d4.type !== 'Retry' || d4.delayMs !== 5000) throw new Error(`${impl} correctness failed on 429 Retry-After`);

  const d5 = evalFn(500, 3, null);
  if (d5.type !== 'Exhausted') throw new Error(`${impl} correctness failed on 500 exhausted`);
}

function benchBackoff(iterations, warmup, round, config, impl) {
  const attempts = [0, 1, 2, 3, 10];
  let sink = 0;
  const base = config.baseDelay;
  const max = config.maxDelay;

  const warmupBatches = Math.max(1, Math.floor(warmup / 5));
  if (impl === 'ts_napi') {
    for (let b = 0; b < warmupBatches; b++) {
      for (let i = 0; i < 5; i++) {
        sink += native.calculateBackoffNative(attempts[i], base, max);
      }
    }
  } else {
    for (let b = 0; b < warmupBatches; b++) {
      for (let i = 0; i < 5; i++) {
        sink += calculateBackoff(attempts[i], config);
      }
    }
  }

  const batches = Math.max(1, Math.floor(iterations / 5));
  const actualIterations = batches * 5;

  const start = performance.now();
  if (impl === 'ts_napi') {
    for (let b = 0; b < batches; b++) {
      for (let i = 0; i < 5; i++) {
        sink += native.calculateBackoffNative(attempts[i], base, max);
      }
    }
  } else {
    for (let b = 0; b < batches; b++) {
      for (let i = 0; i < 5; i++) {
        sink += calculateBackoff(attempts[i], config);
      }
    }
  }
  const end = performance.now();

  const elapsedMs = end - start;
  const elapsedSec = elapsedMs / 1000.0;
  const opsPerSec = actualIterations / elapsedSec;
  const nsPerOp = (elapsedMs * 1e6) / actualIterations;

  if (sink === 0) console.error('Prevent DCE:', sink);

  return {
    workload: 'backoff_deterministic',
    language: impl,
    round,
    iterations: actualIterations,
    elapsed_ms: elapsedMs,
    ops_per_sec: opsPerSec,
    ns_per_op: nsPerOp,
  };
}

function benchPolicy(iterations, warmup, round, config, impl) {
  const testCases = [
    [200, 0, null],
    [404, 0, null],
    [503, 0, null],
    [429, 0, '5'],
    [500, 3, null],
  ];
  let sink = 0;
  const base = config.baseDelay;
  const max = config.maxDelay;
  const maxRetries = config.maxRetries;

  const warmupBatches = Math.max(1, Math.floor(warmup / 5));
  if (impl === 'ts_napi') {
    for (let b = 0; b < warmupBatches; b++) {
      for (let i = 0; i < 5; i++) {
        const tc = testCases[i];
        const d = native.evaluateResponseNative(tc[0], tc[1], base, max, maxRetries, tc[2]);
        sink += d.delayMs || 1;
      }
    }
  } else {
    for (let b = 0; b < warmupBatches; b++) {
      for (let i = 0; i < 5; i++) {
        const tc = testCases[i];
        const d = evaluateResponse(tc[0], tc[1], config, tc[2]);
        sink += d.delayMs || 1;
      }
    }
  }

  const batches = Math.max(1, Math.floor(iterations / 5));
  const actualIterations = batches * 5;

  const start = performance.now();
  if (impl === 'ts_napi') {
    for (let b = 0; b < batches; b++) {
      for (let i = 0; i < 5; i++) {
        const tc = testCases[i];
        const d = native.evaluateResponseNative(tc[0], tc[1], base, max, maxRetries, tc[2]);
        sink += d.delayMs || 1;
      }
    }
  } else {
    for (let b = 0; b < batches; b++) {
      for (let i = 0; i < 5; i++) {
        const tc = testCases[i];
        const d = evaluateResponse(tc[0], tc[1], config, tc[2]);
        sink += d.delayMs || 1;
      }
    }
  }
  const end = performance.now();

  const elapsedMs = end - start;
  const elapsedSec = elapsedMs / 1000.0;
  const opsPerSec = actualIterations / elapsedSec;
  const nsPerOp = (elapsedMs * 1e6) / actualIterations;

  if (sink === 0) console.error('Prevent DCE:', sink);

  return {
    workload: 'retry_policy_evaluation',
    language: impl,
    round,
    iterations: actualIterations,
    elapsed_ms: elapsedMs,
    ops_per_sec: opsPerSec,
    ns_per_op: nsPerOp,
  };
}

function benchCircuit(iterations, warmup, round, impl) {
  let sink = 0;
  const warmupBatches = Math.max(1, Math.floor(warmup / 5));
  const batches = Math.max(1, Math.floor(iterations / 5));
  const actualIterations = batches * 5;

  if (impl === 'ts_napi') {
    const cb = new native.NativeCircuitBreaker(3, 5000);
    for (let b = 0; b < warmupBatches; b++) {
      if (cb.canRequest(1000)) sink += 1;
      cb.recordFailure(1000);
      if (cb.canRequest(2000)) sink += 1;
      cb.recordFailure(2000);
      if (cb.canRequest(3000)) sink += 1;
      cb.recordFailure(3000);
      if (!cb.canRequest(5000)) sink += 1;
      if (cb.canRequest(8001)) sink += 1;
      cb.recordSuccess();
    }

    const start = performance.now();
    for (let b = 0; b < batches; b++) {
      if (cb.canRequest(1000)) sink += 1;
      cb.recordFailure(1000);
      if (cb.canRequest(2000)) sink += 1;
      cb.recordFailure(2000);
      if (cb.canRequest(3000)) sink += 1;
      cb.recordFailure(3000);
      if (!cb.canRequest(5000)) sink += 1;
      if (cb.canRequest(8001)) sink += 1;
      cb.recordSuccess();
    }
    const end = performance.now();
    const elapsedMs = end - start;
    if (sink === 0) console.error('Prevent DCE:', sink);
    return {
      workload: 'circuit_breaker_transitions',
      language: impl,
      round,
      iterations: actualIterations,
      elapsed_ms: elapsedMs,
      ops_per_sec: actualIterations / (elapsedMs / 1000.0),
      ns_per_op: (elapsedMs * 1e6) / actualIterations,
    };
  }

  let clock = 0;
  const realNow = Date.now;
  Date.now = () => clock;
  try {
    const cb = new CircuitBreakerState({ failureThreshold: 3, cooldownMs: 5000 });
    const key = 'api.bench.local';

    for (let b = 0; b < warmupBatches; b++) {
      clock = 1000;
      if (cb.canRequest(key)) sink += 1;
      cb.recordFailure(key);
      clock = 2000;
      if (cb.canRequest(key)) sink += 1;
      cb.recordFailure(key);
      clock = 3000;
      if (cb.canRequest(key)) sink += 1;
      cb.recordFailure(key);
      clock = 5000;
      if (!cb.canRequest(key)) sink += 1;
      clock = 8001;
      if (cb.canRequest(key)) sink += 1;
      cb.recordSuccess(key);
    }

    const start = performance.now();
    for (let b = 0; b < batches; b++) {
      clock = 1000;
      if (cb.canRequest(key)) sink += 1;
      cb.recordFailure(key);
      clock = 2000;
      if (cb.canRequest(key)) sink += 1;
      cb.recordFailure(key);
      clock = 3000;
      if (cb.canRequest(key)) sink += 1;
      cb.recordFailure(key);
      clock = 5000;
      if (!cb.canRequest(key)) sink += 1;
      clock = 8001;
      if (cb.canRequest(key)) sink += 1;
      cb.recordSuccess(key);
    }
    const end = performance.now();
    const elapsedMs = end - start;
    if (sink === 0) console.error('Prevent DCE:', sink);
    return {
      workload: 'circuit_breaker_transitions',
      language: impl,
      round,
      iterations: actualIterations,
      elapsed_ms: elapsedMs,
      ops_per_sec: actualIterations / (elapsedMs / 1000.0),
      ns_per_op: (elapsedMs * 1e6) / actualIterations,
    };
  } finally {
    Date.now = realNow;
  }
}

function parseArgs() {
  const args = process.argv.slice(2);
  let workload = 'backoff_deterministic';
  let iterations = 100000;
  let warmup = 10000;
  let round = 1;
  let impl = 'typescript';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--workload') {
      workload = args[++i];
    } else if (args[i] === '--iterations') {
      iterations = parseInt(args[++i], 10);
    } else if (args[i] === '--warmup') {
      warmup = parseInt(args[++i], 10);
    } else if (args[i] === '--round') {
      round = parseInt(args[++i], 10);
    } else if (args[i] === '--impl') {
      impl = args[++i];
    }
  }

  return { workload, iterations, warmup, round, impl };
}

const config = {
  baseDelay: 100,
  maxDelay: 30000,
  maxRetries: 3,
  jitter: 'none',
};

const { workload, iterations, warmup, round, impl } = parseArgs();

verifyCorrectness(config, impl);

function jsNoop(x) {
  return x;
}

function benchNoop(iterations, warmup, round, impl) {
  const inputs = [1, 2, 3, 4, 5];
  let sink = 0;
  const warmupBatches = Math.max(1, Math.floor(warmup / 5));
  const batches = Math.max(1, Math.floor(iterations / 5));
  const actualIterations = batches * 5;

  if (impl === 'ts_napi') {
    for (let b = 0; b < warmupBatches; b++) {
      for (let i = 0; i < 5; i++) {
        sink += native.noopNative(inputs[i]);
      }
    }
    const start = performance.now();
    for (let b = 0; b < batches; b++) {
      for (let i = 0; i < 5; i++) {
        sink += native.noopNative(inputs[i]);
      }
    }
    const end = performance.now();
    const elapsedMs = end - start;
    if (sink === 0) console.error('Prevent DCE:', sink);
    return {
      workload: 'noop_roundtrip',
      language: impl,
      round,
      iterations: actualIterations,
      elapsed_ms: elapsedMs,
      ops_per_sec: actualIterations / (elapsedMs / 1000.0),
      ns_per_op: (elapsedMs * 1e6) / actualIterations,
    };
  }

  for (let b = 0; b < warmupBatches; b++) {
    for (let i = 0; i < 5; i++) {
      sink += jsNoop(inputs[i]);
    }
  }
  const start = performance.now();
  for (let b = 0; b < batches; b++) {
    for (let i = 0; i < 5; i++) {
      sink += jsNoop(inputs[i]);
    }
  }
  const end = performance.now();
  const elapsedMs = end - start;
  if (sink === 0) console.error('Prevent DCE:', sink);
  return {
    workload: 'noop_roundtrip',
    language: impl,
    round,
    iterations: actualIterations,
    elapsed_ms: elapsedMs,
    ops_per_sec: actualIterations / (elapsedMs / 1000.0),
    ns_per_op: (elapsedMs * 1e6) / actualIterations,
  };
}

let result;
if (workload === 'backoff_deterministic') {
  result = benchBackoff(iterations, warmup, round, config, impl);
} else if (workload === 'retry_policy_evaluation') {
  result = benchPolicy(iterations, warmup, round, config, impl);
} else if (workload === 'circuit_breaker_transitions') {
  result = benchCircuit(iterations, warmup, round, impl);
} else if (workload === 'noop_roundtrip') {
  result = benchNoop(iterations, warmup, round, impl);
} else {
  console.error(`Unknown workload: ${workload}`);
  process.exit(1);
}

console.log(JSON.stringify(result));
