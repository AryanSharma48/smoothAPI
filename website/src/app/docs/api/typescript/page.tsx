export default function TSApiPage() {
  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">API Reference: TypeScript</h2>

      <h3 className="text-2xl font-bold mt-8 mb-4 font-mono text-rose-300">createSmoothFetch(config)</h3>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        The primary entry point for the TypeScript SDK. Returns a decorated fetch function that implements the self-healing patterns configured.
      </p>
      
      <h4 className="text-xl font-bold mt-6 mb-3">Arguments</h4>
      <ul className="list-disc pl-6 text-slate-300 space-y-2 mb-6">
        <li><strong>config</strong> (<code>SmoothFetchConfig</code>): The configuration object.</li>
      </ul>

      <h4 className="text-xl font-bold mt-6 mb-3">Returns</h4>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        <code>(input: RequestInfo | URL, init?: RequestInit) =&gt; Promise&lt;Response | any&gt;</code>: A drop-in replacement for the native <code>fetch</code> API. If a fallback is triggered, it may return the fallback object directly instead of a Response object.
      </p>

      <hr className="border-slate-800 my-8" />

      <h3 className="text-2xl font-bold mt-8 mb-4">SmoothFetchConfig (Interface)</h3>
      <div className="overflow-x-auto mb-8">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead>
            <tr className="text-slate-400 text-left">
              <th className="py-3 px-4 font-mono">Property</th>
              <th className="py-3 px-4 font-mono">Type</th>
              <th className="py-3 px-4">Required</th>
              <th className="py-3 px-4">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">backoff</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">BackoffConfig</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">Yes</td>
              <td className="py-3.5 px-4 text-slate-300">Configuration for retries and delays.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">circuitBreaker</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">CircuitBreakerConfig</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">Yes</td>
              <td className="py-3.5 px-4 text-slate-300">Configuration for failure thresholds.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">fallback</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">any</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">No</td>
              <td className="py-3.5 px-4 text-slate-300">Data to return when the circuit trips or errors are exhausted.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">timeoutMs</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">number</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">No</td>
              <td className="py-3.5 px-4 text-slate-300">Automatically abort requests that take longer than this duration (in milliseconds).</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
