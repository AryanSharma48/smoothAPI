/**
 * This is an example of how to use smoothapi with express.
 * Instructions on how to run this example can be found in the README.md file
 * associated with this /example/express folder
 */

import express from 'express';
import { createSmoothFetch } from '@codingaryan/smoothapi';
import dotenv from 'dotenv';

dotenv.config();
const app = express();
const PORT = process.env.PORT || 3002;
const SANDBOX_URL = process.env.SANDBOX_URL || 'http://localhost:3001';

/* 
Can create a smooth fetch instance with default options:
    - Retries: 3 attempts
    - Backoff Base Delay: 100 milliseconds
    - Circuit Failure Threshold: Trips after 3 consecutive failures
    - Circuit Cooldown: Stays open for 10 seconds before probing
    - Status Codes to Retry: 429, 500, 502, 503, and 504
    - Timeout: 5000 milliseconds
*/
const defaultSmoothFetch = createSmoothFetch({ timeoutMs: 5000 });

/*
Or could create a smooth fetch instance with custom options
*/
const customSmoothFetch = createSmoothFetch({
        backoff: {
            baseDelay: 100,      // ms to wait before first retry
            maxDelay: 30000,     // cap on exponential growth
            maxRetries: 3        // max number of retry attempts
        },
        circuitBreaker: {
            failureThreshold: 1, // trip OPEN after 1 consecutive failures
            cooldownMs: 30000    // stay OPEN for 30 seconds before probing
        },
        // Optional: Return this instead of throwing when the circuit is OPEN
        fallback: { error: "Service degraded. Circuit is OPEN, returning stale data." },
        // Optional: Custom status codes to retry on
        retryOn: [429, 500, 502, 503, 504],
        // Optional: Abort a request attempt if it takes longer than 5000ms
        timeoutMs: 5000
});

const dedupSmoothFetch = createSmoothFetch({
    deduplication: {}
});

// Timeout integration: aborts individual attempts exceeding 1000ms, retrying with backoff
const timeoutSmoothFetch = createSmoothFetch({
    timeoutMs: 1000,
    backoff: {
        baseDelay: 200,
        maxRetries: 2,
    },
    fallback: {
        source: 'fallback',
        message: 'Upstream timed out after retries. Graceful fallback returned.'
    },
    onRetry: (context) => {
        console.log(`[timeout-demo] Attempt #${context.attempt} timed out. Retrying in ${context.delayMs}ms...`);
    }
});

// Backoff integration: demonstrates exponential backoff with equal jitter and retry inspection
const backoffSmoothFetch = createSmoothFetch({
    backoff: {
        baseDelay: 250,
        maxDelay: 4000,
        maxRetries: 3,
        jitter: 'equal' // exponential backoff with equal jitter to prevent thundering herds
    },
    retryOn: [429, 500, 502, 503, 504],
    onRetry: (context) => {
        console.log(`[backoff-demo] Retry attempt #${context.attempt}/${context.maxRetries} after delay of ${context.delayMs}ms for ${context.url}`);
    }
});

app.use(express.json());

app.get('/', (_req, res) => {
    // The root endpoint of the example express server.
    res.json({ 
        message: 'Welcome to the SmoothAPI Express Example!',
        description: 'Demonstrates retries, circuit breakers, fallback handling, request deduplication, timeouts, and backoff using SmoothAPI.',
        endpoints: {
            retry_demo: '/retry-demo',
            circuit_demo: '/circuit-demo',
            dedup_demo: '/dedup-demo',
            timeout_demo: '/timeout-demo',
            backoff_demo: '/backoff-demo',
        },
    });
});

app.get('/retry-demo', async (_req, res) => {
    // This route targets the sandbox's flaky /unstable-data endpoint.
    // SmoothAPI will retry transient failures and return a successful response
    // when the upstream recovers, or return an error if retries are exhausted.
    try {
        // Drop-in replacement for native fetch, using DEFAULT options
        const result = await defaultSmoothFetch(`${SANDBOX_URL}/unstable-data`) as any;
        
        if (!result.ok) {
            return res.status(502).json({ error: `Upstream failed with status ${result.status}` });
        }

        const data = await result.json().catch(() => null);
        return res.json({ 
            source: 'upstream-response', 
            status: result.status, 
            data 
        });
    } catch (error) {
        return res.status(502).json({
            error: error instanceof Error ? error.message : String(error),
        });
    }
});

app.get('/circuit-demo', async (_req, res) => {
    // This route targets the sandbox's always-failing endpoint.
    // Repeated failures will trip the circuit breaker, after which SmoothAPI
    // short-circuits the request and returns the configured fallback value.
    // Refresh the page to see the circuit breaker in action, and wait for 30 seconds to see it reset.
    try {
        // Drop-in replacement for native fetch, using CUSTOM options
        const result = await customSmoothFetch(`${SANDBOX_URL}/always-fail`);

        if ('ok' in result && !result.ok) {
            return res.status(502).json({ error: `Upstream failed with status ${(result as any).status}` });
        }

        // After initial failure, circuit-breaker will OPEN, and SmoothAPI will return the configured fallback value
        if ('error' in result) {
            console.log('Circuit is OPEN, returning fallback response');
            return res.json({ source: 'fallback', data: result });
        }

        // If the upstream recovers, SmoothAPI will return the successful response
        // (strictly speaking, this won't happen in this example since the upstream always fails)
        const data = await result.json().catch(() => null);
        return res.json({ source: 'upstream-response', status: result.status, data });
    } catch (error) {
        return res.status(502).json({
            error: error instanceof Error ? error.message : String(error),
        });
    }
});

app.get('/dedup-demo', async (_req, res) => {
    try {
        const [response1 , response2, response3] = await Promise.all([
            dedupSmoothFetch(`${SANDBOX_URL}/health`) as any,
            dedupSmoothFetch(`${SANDBOX_URL}/health`) as any,
            dedupSmoothFetch(`${SANDBOX_URL}/health`) as any,
        ]);

        const [data1, data2, data3] = await Promise.all([
            response1.json(),
            response2.json(),
            response3.json(),
        ]);

        return res.json({
            message: 'Three identical requests were made concurrently.',
            results: [data1, data2, data3],
        });
    } catch (error) {
        return res.status(502).json({
            error: error instanceof Error ? error.message : String(error),
        });
    }
});

app.get('/timeout-demo', async (_req, res) => {
    // This route targets the sandbox's /delayed endpoint with a delay of 2500ms.
    // Since timeoutSmoothFetch has timeoutMs: 1000, each attempt will abort after 1000ms.
    // After exhausting retries, it returns the configured graceful fallback.
    const startTime = Date.now();
    try {
        const result = await timeoutSmoothFetch(`${SANDBOX_URL}/delayed?ms=2500`);
        const duration = Date.now() - startTime;

        if (result instanceof Response) {
            const data = await result.json().catch(() => null);
            return res.json({
                feature: 'timeoutMs',
                source: 'upstream-response',
                durationMs: duration,
                data
            });
        }

        return res.json({
            feature: 'timeoutMs',
            source: 'fallback',
            durationMs: duration,
            note: 'Requests timed out (>1000ms) and were safely recovered via fallback',
            data: result
        });
    } catch (error) {
        return res.status(504).json({
            feature: 'timeoutMs',
            durationMs: Date.now() - startTime,
            error: error instanceof Error ? error.message : String(error)
        });
    }
});

app.get('/backoff-demo', async (_req, res) => {
    // Demonstrates exponential backoff with equal jitter and retry inspection.
    // Targets the flaky /unstable-data endpoint.
    const retryHistory: Array<{ attempt: number; delayMs: number }> = [];
    const trackingFetch = createSmoothFetch({
        backoff: {
            baseDelay: 200,
            maxDelay: 3000,
            maxRetries: 3,
            jitter: 'equal'
        },
        retryOn: [429, 500, 502, 503, 504],
        onRetry: (ctx) => {
            retryHistory.push({ attempt: ctx.attempt, delayMs: ctx.delayMs });
        }
    });

    const startTime = Date.now();
    try {
        const result = await trackingFetch(`${SANDBOX_URL}/unstable-data`);
        const duration = Date.now() - startTime;

        if (result instanceof Response) {
            const data = await result.json().catch(() => null);
            return res.json({
                feature: 'backoff_with_jitter',
                status: result.status,
                totalDurationMs: duration,
                retriesPerformed: retryHistory.length,
                retryHistory,
                data
            });
        }

        return res.json({
            feature: 'backoff_with_jitter',
            source: 'fallback',
            totalDurationMs: duration,
            retriesPerformed: retryHistory.length,
            retryHistory,
            data: result
        });
    } catch (error) {
        return res.status(502).json({
            feature: 'backoff_with_jitter',
            totalDurationMs: Date.now() - startTime,
            retriesPerformed: retryHistory.length,
            retryHistory,
            error: error instanceof Error ? error.message : String(error)
        });
    }
});

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.listen(PORT, () => {
  console.log(`[express-example] listening on http://localhost:${PORT}`);
});