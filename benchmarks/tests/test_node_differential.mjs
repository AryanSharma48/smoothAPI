// Differential runner: Native TypeScript and TypeScript -> Node-API -> Rust.
//
// Usage: node benchmarks/tests/test_node_differential.mjs --impl ts_native|ts_napi [vectors.json]
//
// Native TS exercises PRODUCTION code paths only:
//   - backoff:        calculateBackoff() with jitter 'none'
//   - retry policy:   createSmoothFetch() driven by a mocked fetch; decisions are read
//                     from public lifecycle hooks (onRetry / onSuccess / onFailure)
//   - circuit:        CircuitBreakerState with an injected Date.now clock
// No production source is modified; globals are patched only inside this process.
//
// Outputs raw observations as JSON. Scoring happens in scripts/run_differential.py.

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const require = createRequire(import.meta.url);

const args = process.argv.slice(2);
const implIdx = args.indexOf('--impl');
const impl = implIdx >= 0 ? args[implIdx + 1] : 'ts_native';
const vectorsPath = args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--impl')
  ?? path.join(root, 'benchmarks', 'config', 'differential_vectors.json');
const doc = JSON.parse(readFileSync(vectorsPath, 'utf8'));

// ── Integer representation helpers ─────────────────────────────────────────────
// Inputs arrive as decimal strings. JS numbers cannot represent every integer above
// 2^53, so record when conversion is lossy instead of silently hiding it.
function toNumber(decimal) {
  const n = Number(decimal);
  const lossy = !Number.isFinite(n) || BigInt(Math.trunc(n)) !== BigInt(decimal);
  return { n, lossy };
}

function numberToDecimal(n) {
  if (typeof n !== 'number') return String(n);
  if (!Number.isFinite(n)) return String(n);
  if (Number.isInteger(n)) return BigInt(n).toString();
  return String(n);
}

// ── Native TS adapters ────────────────────────────────────────────────────────
async function loadNative() {
  const distRoot = path.join(root, 'packages', 'smooth-api-ts', 'dist');
  const backoff = await import(pathToUrl(path.join(distRoot, 'utils', 'backoff.js')));
  const index = await import(pathToUrl(path.join(distRoot, 'index.js')));
  return { calculateBackoff: backoff.calculateBackoff, ...index };
}

function pathToUrl(p) {
  return new URL(`file:///${p.replace(/\\/g, '/')}`).href;
}

async function nativeAdapter() {
  const ts = await loadNative();

  return {
    backoff(base, max, attempt) {
      return ts.calculateBackoff(attempt, { baseDelay: base, maxDelay: max, jitter: 'none' });
    },

    jitter(v) {
      const base = Number(v.base_delay_ms);
      const max = Number(v.max_delay_ms);
      const prev = v.prev_delay_ms !== null ? Number(v.prev_delay_ms) : undefined;
      const cfg = v.strategy === 'default'
        ? { baseDelay: base, maxDelay: max }
        : { baseDelay: base, maxDelay: max, jitter: v.strategy };
      return Math.floor(ts.calculateBackoff(v.attempt, cfg, prev, v.random_factor));
    },

    async retry(vec, cfg) {
      // Drive the real fetch pipeline: `attempt` prior retryable 503s, then the target status.
      const sequence = [];
      for (let i = 0; i < vec.attempt; i++) sequence.push({ status: 503, retryAfter: null });
      sequence.push({ status: vec.status, retryAfter: vec.retry_after });

      let call = 0;
      const realFetch = globalThis.fetch;
      const realSetTimeout = globalThis.setTimeout;
      const realClearTimeout = globalThis.clearTimeout;
      globalThis.fetch = async () => {
        const spec = sequence[Math.min(call, sequence.length - 1)];
        call++;
        const headers = spec.retryAfter !== null ? { 'Retry-After': spec.retryAfter } : {};
        const nullBody = [204, 304].includes(spec.status);
        return new Response(nullBody ? null : '', { status: spec.status, headers });
      };
      // Instant sleeps: the delay value is observed via onRetry, not by waiting.
      globalThis.setTimeout = (fn) => { queueMicrotask(fn); return 0; };
      globalThis.clearTimeout = () => {};

      const events = { retries: [], success: null, failure: null };
      try {
        const smoothFetch = ts.createSmoothFetch({
          backoff: {
            baseDelay: Number(cfg.base_delay_ms),
            maxDelay: Number(cfg.max_delay_ms),
            maxRetries: vec.max_retries,
            jitter: 'none',
          },
          circuitBreaker: { failureThreshold: 1_000_000 },
          onRetry: (ctx) => events.retries.push(ctx),
          onSuccess: (ctx) => { events.success = ctx; },
          onFailure: (ctx) => { events.failure = ctx; },
        });
        await smoothFetch(`http://diff.test/${vec.id}`);
      } finally {
        globalThis.fetch = realFetch;
        globalThis.setTimeout = realSetTimeout;
        globalThis.clearTimeout = realClearTimeout;
      }

      const target = events.retries.find((r) => r.attempt === vec.attempt + 1);
      const raw = {
        fetch_calls: call,
        on_success: events.success !== null,
        on_failure_message: events.failure?.error?.message ?? null,
      };
      if (target) return { decision: 'Retry', delay_ms: numberToDecimal(target.delayMs), raw };
      if (events.success) return { decision: 'Success', raw };
      if (events.failure && /Retries exhausted/.test(events.failure.error?.message ?? '')) {
        return { decision: 'Exhausted', raw };
      }
      if (events.failure) return { decision: 'Terminal', raw };
      return { decision: 'Unobserved', raw };
    },

    circuit(vec) {
      let clock = 0;
      const realNow = Date.now;
      Date.now = () => clock;
      try {
        const cb = new ts.CircuitBreakerState({
          failureThreshold: vec.failure_threshold,
          cooldownMs: vec.cooldown_ms,
        });
        const key = 'diff.test';
        return vec.steps.map((step) => {
          clock = step.t;
          const obs = {};
          if (step.op === 'record_failure') cb.recordFailure(key);
          else if (step.op === 'record_success') cb.recordSuccess(key);
          else if (step.op === 'release_probe') cb.releaseProbe(key);
          else if (step.op === 'can_request') obs.ret = cb.canRequest(key);
          const stats = cb.getStats(key);
          obs.state = cb.getStoredState(key);
          obs.state_at = cb.getStateAt(key, step.t);
          obs.failure_count = stats.failureCount;
          return obs;
        });
      } finally {
        Date.now = realNow;
      }
    },
  };
}

// ── Node-API adapter ─────────────────────────────────────────────────────────
function napiAdapter() {
  const native = require(path.join(root, 'bindings', 'node'));
  return {
    backoff(base, max, attempt) {
      return native.calculateBackoffNative(attempt, base, max);
    },
    jitter(v) {
      const base = Number(v.base_delay_ms);
      const max = Number(v.max_delay_ms);
      const prev = v.prev_delay_ms !== null ? Number(v.prev_delay_ms) : null;
      return native.calculateBackoffNative(v.attempt, base, max, v.strategy, prev, v.random_factor);
    },
    async retry(vec, cfg) {
      const d = native.evaluateResponseNative(
        vec.status, vec.attempt,
        Number(cfg.base_delay_ms), Number(cfg.max_delay_ms),
        vec.max_retries, vec.retry_after,
      );
      return d.type === 'Retry'
        ? { decision: d.type, delay_ms: numberToDecimal(d.delayMs) }
        : { decision: d.type };
    },
    circuit(vec) {
      const cb = new native.NativeCircuitBreaker(vec.failure_threshold, vec.cooldown_ms);
      return vec.steps.map((step) => {
        const obs = {};
        if (step.op === 'record_failure') cb.recordFailure(step.t);
        else if (step.op === 'record_success') cb.recordSuccess();
        else if (step.op === 'release_probe') cb.releaseProbe();
        else if (step.op === 'can_request') obs.ret = cb.canRequest(step.t);
        obs.state = cb.state;
        obs.state_at = cb.stateAt(step.t);
        obs.failure_count = cb.failureCount;
        return obs;
      });
    },
  };
}

// ── Runner ───────────────────────────────────────────────────────────────────
function runBackoffSuite(adapter, list) {
  const out = {};
  for (const v of list) {
    const base = toNumber(v.base_delay_ms);
    const max = toNumber(v.max_delay_ms);
    try {
      const val = adapter.backoff(base.n, max.n, v.attempt);
      out[v.id] = { value: numberToDecimal(val), input_lossy: base.lossy || max.lossy };
    } catch (err) {
      out[v.id] = { error: String(err?.message ?? err), input_lossy: base.lossy || max.lossy };
    }
  }
  return out;
}

function runJitterSuite(adapter, list) {
  const out = {};
  for (const v of list) {
    try {
      const val = adapter.jitter(v);
      out[v.id] = { value: numberToDecimal(val) };
    } catch (err) {
      out[v.id] = { error: String(err?.message ?? err) };
    }
  }
  return out;
}

async function main() {
  const adapter = impl === 'ts_napi' ? napiAdapter() : await nativeAdapter();
  const results = {
    backoff: runBackoffSuite(adapter, doc.backoff),
    jitter: runJitterSuite(adapter, doc.jitter ?? []),
    backoff_numeric_boundary: runBackoffSuite(adapter, doc.backoff_numeric_boundary ?? []),
    retry_policy: {},
    circuit_breaker: {},
  };

  for (const v of doc.retry_policy) {
    try {
      results.retry_policy[v.id] = await adapter.retry(v, doc.retry_policy_config);
    } catch (err) {
      results.retry_policy[v.id] = { error: String(err?.message ?? err) };
    }
  }

  for (const v of doc.circuit_breaker) {
    try {
      results.circuit_breaker[v.id] = adapter.circuit(v);
    } catch (err) {
      results.circuit_breaker[v.id] = [{ error: String(err?.message ?? err) }];
    }
  }

  process.stdout.write(JSON.stringify({ impl, results }) + '\n');
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});

