import { createSmoothFetch } from "@codingaryan/smoothapi";

const retryButton = document.getElementById("retry-btn");
const circuitButton = document.getElementById("circuit-btn");
const output = document.getElementById("output");

const retryFallback = {
    data: "cached fallback (stale)"
};

const circuitFallback = {
    data: "circuit-open fallback"
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