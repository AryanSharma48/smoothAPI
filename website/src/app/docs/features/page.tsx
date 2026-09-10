export default function FeaturesPage() {
  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">Core Features</h2>
      <div className="space-y-8">
        
        <div className="border-l-4 border-rose-500 pl-4 py-1">
          <h3 className="text-xl font-bold text-slate-200 mb-2">Exponential Backoff & Full Jitter</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Retries transient failures with exponentially increasing delays. Generates randomized &quot;jitter&quot; boundaries to prevent client requests from hammering recovering endpoints in sync (the &quot;thundering herd&quot; problem).
          </p>
        </div>

        <div className="border-l-4 border-rose-500 pl-4 py-1">
          <h3 className="text-xl font-bold text-slate-200 mb-2">Per-Domain Circuit Breaker</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Tracks API health in isolated state machines. If a specific domain reaches your failure threshold, the circuit trips to `OPEN`, immediately blocking further connections and returning fallback data. This prevents resource starvation and cascading failures.
          </p>
        </div>

        <div className="border-l-4 border-rose-500 pl-4 py-1">
          <h3 className="text-xl font-bold text-slate-200 mb-2">Graceful Client-Error Fallbacks</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Support for `fallbackOnNonRetryable` / `fallback_on_non_retryable`. Safely intercept non-retryable client-side HTTP codes (like 404, 403, 400) and return custom data, show browser alerts, or fire custom notification callbacks instead of throwing app-breaking crashes.
          </p>
        </div>

        <div className="border-l-4 border-rose-500 pl-4 py-1">
          <h3 className="text-xl font-bold text-slate-200 mb-2">Request Deduplication</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Automatically detects multiple concurrent identical requests and coalesces them into a single network call. Once the shared call completes, the response is delivered to all waiting callers, saving bandwidth and compute.
          </p>
        </div>

        <div className="border-l-4 border-rose-500 pl-4 py-1">
          <h3 className="text-xl font-bold text-slate-200 mb-2">Request Timeouts</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Configurable timeouts to automatically abort requests that hang indefinitely, triggering a retry or failing fast instead of holding connections open endlessly.
          </p>
        </div>

      </div>
    </div>
  );
}
