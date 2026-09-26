import { createSmoothFetch } from "@codingaryan/smoothapi";

const retryButton = document.getElementById("retry-btn");
const circuitButton = document.getElementById("circuit-btn");
const timeoutButton = document.getElementById("timeout-btn");
const backoffButton = document.getElementById("backoff-btn");
const output = document.getElementById("output");

const retryFallback = {
    data: "cached fallback (stale)"
};

const circuitFallback = {
    data: "circuit-open fallback"
};

const timeoutFallback = {
    data: "timeout fallback (slow upstream recovered)"
};

const retryFetch = createSmoothFetch({
    retryOn: [429, 500, 502, 503, 504],
    fallback: retryFallback,
    fallbackOnNonRetryable: true
});

const circuitFetch = createSmoothFetch({
    retryOn: [429, 500, 502, 503, 504],
    circuitBreaker: {
        failureThreshold: 3,
        cooldownMs: 5000
    },
    fallback: circuitFallback
});

// Demonstrates timeoutMs aborting attempts taking longer than 1000ms
const timeoutFetch = createSmoothFetch({
    timeoutMs: 1000,
    backoff: {
        baseDelay: 200,
        maxRetries: 2
    },
    fallback: timeoutFallback
});

retryButton?.addEventListener("click", async () => {
    if (!output) return;

    output.textContent = "Running retry demo...";

    try {
        const result = await retryFetch(
            "http://localhost:3001/unstable-data"
        );

        if (result instanceof Response) {
            const data = await result.json().catch(() => null);

            output.textContent = JSON.stringify(
                {
                    source: "live",
                    status: result.status,
                    data
                },
                null,
                2
            );
        } else {
            output.textContent = JSON.stringify(
                {
                    source: "fallback",
                    data: result
                },
                null,
                2
            );
        }
    } catch (error) {
        output.textContent = `Error: ${error}`;
    }
});

circuitButton?.addEventListener("click", async () => {
    if (!output) return;

    output.textContent = "Running circuit breaker demo...";

    try {
        const result = await circuitFetch(
            "http://localhost:3001/always-fail"
        );

        if (result instanceof Response) {
            output.textContent = JSON.stringify(
                {
                    hitNetwork: true,
                    status: result.status
                },
                null,
                2
            );
        } else {
            output.textContent = JSON.stringify(
                {
                    hitNetwork: false,
                    data: result
                },
                null,
                2
            );
        }
    } catch (error) {
        output.textContent = `Error: ${error}`;
    }
});

timeoutButton?.addEventListener("click", async () => {
    if (!output) return;

    output.textContent = "Calling delayed upstream (2500ms) with timeoutMs: 1000...\nPer-attempt timeout will abort slow requests and fall back gracefully.";

    const startTime = Date.now();
    try {
        const result = await timeoutFetch(
            "http://localhost:3001/delayed?ms=2500"
        );
        const duration = Date.now() - startTime;

        if (result instanceof Response) {
            const data = await result.json().catch(() => null);
            output.textContent = JSON.stringify(
                {
                    feature: "timeoutMs",
                    source: "live",
                    durationMs: duration,
                    status: result.status,
                    data
                },
                null,
                2
            );
        } else {
            output.textContent = JSON.stringify(
                {
                    feature: "timeoutMs",
                    source: "fallback",
                    durationMs: duration,
                    note: "Request aborted at 1000ms limit, fallback returned safely.",
                    data: result
                },
                null,
                2
            );
        }
    } catch (error) {
        output.textContent = `Timeout Error: ${error}`;
    }
});

backoffButton?.addEventListener("click", async () => {
    if (!output) return;

    const logs: string[] = ["Running exponential backoff with equal jitter demo..."];
    output.textContent = logs.join("\n");

    const backoffFetch = createSmoothFetch({
        backoff: {
            baseDelay: 250,
            maxDelay: 3000,
            maxRetries: 3,
            jitter: "equal"
        },
        retryOn: [429, 500, 502, 503, 504],
        onRetry: (ctx) => {
            logs.push(`[onRetry] Attempt #${ctx.attempt}/${ctx.maxRetries} failed with status ${ctx.status || 'network error'}. Backing off for ${Math.round(ctx.delayMs)}ms...`);
            output.textContent = logs.join("\n");
        }
    });

    try {
        const startTime = Date.now();
        const result = await backoffFetch("http://localhost:3001/unstable-data");
        const duration = Date.now() - startTime;

        if (result instanceof Response) {
            const data = await result.json().catch(() => null);
            logs.push(`\n[Success] Resolved in ${duration}ms with status ${result.status}:`);
            logs.push(JSON.stringify(data, null, 2));
        } else {
            logs.push(`\n[Fallback] Resolved in ${duration}ms:`);
            logs.push(JSON.stringify(result, null, 2));
        }
        output.textContent = logs.join("\n");
    } catch (error) {
        logs.push(`\n[Exhausted] Failed: ${error}`);
        output.textContent = logs.join("\n");
    }
});