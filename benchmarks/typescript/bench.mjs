import { calculateBackoff } from '../../packages/smooth-api-ts/dist/utils/backoff.js';
import { performance } from 'node:perf_hooks';

const DEFAULT_RETRY_ON = [429, 500, 502, 503, 504];

function evaluateResponse(status, attempt, config, retryAfterHeader) {
  if (status >= 200 && status < 300) {
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
    const parsed = parseInt(retryAfterHeader, 10);
    if (!Number.isNaN(parsed) && parsed > 0) {
      delayMs = parsed * 1000;
    }
  }
  return { type: 'Retry', delayMs };
}

function verifyCorrectness(config) {
  const expectedBackoffs = [
    [0, 100],
    [1, 200],
    [2, 400],
    [3, 800],
    [10, 30000],
  ];

  for (const [attempt, expected] of expectedBackoffs) {
    const delay = calculateBackoff(attempt, config);
    if (delay !== expected) {
      throw new Error(`TS correctness failed: attempt ${attempt} returned ${delay}, expected ${expected}`);
    }
  }

  const d1 = evaluateResponse(200, 0, config, null);
  if (d1.type !== 'Success') throw new Error('TS correctness failed on 200');

  const d2 = evaluateResponse(404, 0, config, null);
  if (d2.type !== 'Terminal') throw new Error('TS correctness failed on 404');

  const d3 = evaluateResponse(503, 0, config, null);
  if (d3.type !== 'Retry' || d3.delayMs !== 100) throw new Error('TS correctness failed on 503');

  const d4 = evaluateResponse(429, 0, config, '5');
  if (d4.type !== 'Retry' || d4.delayMs !== 5000) throw new Error('TS correctness failed on 429 Retry-After');

  const d5 = evaluateResponse(500, 3, config, null);
  if (d5.type !== 'Exhausted') throw new Error('TS correctness failed on 500 exhausted');
}

function benchBackoff(iterations, warmup, round, config) {
  const attempts = [0, 1, 2, 3, 10];
  const numAttempts = attempts.length;
  let sink = 0;

  // Warm-up to trigger V8 JIT tier-up
  for (let i = 0; i < warmup; i++) {
    sink += calculateBackoff(attempts[i % numAttempts], config);
  }

  // Timed execution
  const start = performance.now();
  for (let i = 0; i < iterations; i++) {
    sink += calculateBackoff(attempts[i % numAttempts], config);
  }
  const end = performance.now();

  const elapsedMs = end - start;
  const elapsedSec = elapsedMs / 1000.0;
  const opsPerSec = iterations / elapsedSec;
  const nsPerOp = (elapsedMs * 1e6) / iterations;

  if (sink === 0) console.error("Prevent DCE:", sink);

  return {
    workload: 'backoff_deterministic',
    language: 'typescript',
    round,
    iterations,
    elapsed_ms: elapsedMs,
    ops_per_sec: opsPerSec,
    ns_per_op: nsPerOp,
  };
}

function benchPolicy(iterations, warmup, round, config) {
  const testCases = [
    [200, 0, null],
    [404, 0, null],
    [503, 0, null],
    [429, 0, '5'],
    [500, 3, null],
  ];
  const numCases = testCases.length;
  let sink = 0;

  // Warm-up
  for (let i = 0; i < warmup; i++) {
    const c = testCases[i % numCases];
    const r = evaluateResponse(c[0], c[1], config, c[2]);
    sink += r.delayMs || 1;
  }

  // Timed execution
  const start = performance.now();
  for (let i = 0; i < iterations; i++) {
    const c = testCases[i % numCases];
    const r = evaluateResponse(c[0], c[1], config, c[2]);
    sink += r.delayMs || 1;
  }
  const end = performance.now();

  const elapsedMs = end - start;
  const elapsedSec = elapsedMs / 1000.0;
  const opsPerSec = iterations / elapsedSec;
  const nsPerOp = (elapsedMs * 1e6) / iterations;

  if (sink === 0) console.error("Prevent DCE:", sink);

  return {
    workload: 'retry_policy_evaluation',
    language: 'typescript',
    round,
    iterations,
    elapsed_ms: elapsedMs,
    ops_per_sec: opsPerSec,
    ns_per_op: nsPerOp,
  };
}

function main() {
  const args = process.argv.slice(2);
  let workload = 'backoff_deterministic';
  let iterations = 100000;
  let warmup = 10000;
  let round = 1;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--workload') workload = args[++i];
    else if (args[i] === '--iterations') iterations = parseInt(args[++i], 10);
    else if (args[i] === '--warmup') warmup = parseInt(args[++i], 10);
    else if (args[i] === '--round') round = parseInt(args[++i], 10);
  }

  const config = {
    baseDelay: 100,
    maxDelay: 30000,
    maxRetries: 3,
    jitter: 'none',
  };

  verifyCorrectness(config);

  let result;
  if (workload === 'backoff_deterministic') {
    result = benchBackoff(iterations, warmup, round, config);
  } else if (workload === 'retry_policy_evaluation') {
    result = benchPolicy(iterations, warmup, round, config);
  } else {
    console.error(`Unknown workload: ${workload}`);
    process.exit(1);
  }

  console.log(JSON.stringify(result));
}

main();
