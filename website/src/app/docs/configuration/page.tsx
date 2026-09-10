export default function ConfigurationPage() {
  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">Configuration Options</h2>
      <p className="text-slate-300 mb-6">
        Customize the behavior of `SmoothAPI` using the following properties when initializing:
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead>
            <tr className="text-slate-400 text-left">
              <th className="py-3 px-4 font-mono">Property</th>
              <th className="py-3 px-4 font-mono">Type</th>
              <th className="py-3 px-4">Default</th>
              <th className="py-3 px-4">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">backoff.baseDelay</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">number</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">100 / 0.1</td>
              <td className="py-3.5 px-4 text-slate-300">Initial wait time before the first retry (ms in TS, seconds in Python).</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">backoff.maxRetries</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">number</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">3</td>
              <td className="py-3.5 px-4 text-slate-300">Maximum number of attempts to resolve the request.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">circuitBreaker.failureThreshold</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">number</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">3</td>
              <td className="py-3.5 px-4 text-slate-300">Consecutive failures needed to trip the circuit to OPEN.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">circuitBreaker.cooldownMs</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">number</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">10000</td>
              <td className="py-3.5 px-4 text-slate-300">Time to wait (in ms) before entering HALF_OPEN probe state.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">fallback</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">any</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">undefined</td>
              <td className="py-3.5 px-4 text-slate-300">Object returned immediately on an OPEN circuit or client error fallback.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">fallbackOnNonRetryable</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">boolean</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">false</td>
              <td className="py-3.5 px-4 text-slate-300">If true, returns fallbacks or mock responses on non-retryable client codes (e.g. 404, 401).</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">onNonRetryableError</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">function</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">undefined</td>
              <td className="py-3.5 px-4 text-slate-300">Custom callback fired when a client-error occurs. Disables default browser alerts.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">timeoutMs / timeout_ms</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">number</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">undefined</td>
              <td className="py-3.5 px-4 text-slate-300">Maximum time (in ms) to wait for a request before aborting and retrying.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">deduplication</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">object</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">undefined</td>
              <td className="py-3.5 px-4 text-slate-300">Configuration object to enable coalescing concurrent identical requests.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
