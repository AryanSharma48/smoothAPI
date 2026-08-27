export default function PyApiPage() {
  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">API Reference: Python</h2>

      <h3 className="text-2xl font-bold mt-8 mb-4 font-mono text-rose-300">@smooth_api(config)</h3>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        The primary entry point for the Python SDK. A decorator that wraps standard functions or async functions (<code>async def</code>) with self-healing patterns.
      </p>
      
      <h4 className="text-xl font-bold mt-6 mb-3">Arguments</h4>
      <ul className="list-disc pl-6 text-slate-300 space-y-2 mb-6">
        <li><strong>config</strong> (<code>SmoothConfig</code>): The configuration object.</li>
      </ul>

      <h4 className="text-xl font-bold mt-6 mb-3">Returns</h4>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        The wrapped function. It catches exceptions (like <code>requests.exceptions.RequestException</code> or <code>httpx.HTTPError</code>) and manages backoff automatically.
      </p>

      <hr className="border-slate-800 my-8" />

      <h3 className="text-2xl font-bold mt-8 mb-4">SmoothConfig (Class)</h3>
      <div className="overflow-x-auto mb-8">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead>
            <tr className="text-slate-400 text-left">
              <th className="py-3 px-4 font-mono">Parameter</th>
              <th className="py-3 px-4 font-mono">Type</th>
              <th className="py-3 px-4">Default</th>
              <th className="py-3 px-4">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">base_delay</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">float</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">0.1</td>
              <td className="py-3.5 px-4 text-slate-300">Initial delay in seconds.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">max_retries</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">int</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">3</td>
              <td className="py-3.5 px-4 text-slate-300">Maximum number of retry attempts.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">failure_threshold</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">int</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">3</td>
              <td className="py-3.5 px-4 text-slate-300">Consecutive failures before tripping the circuit.</td>
            </tr>
            <tr>
              <td className="py-3.5 px-4 font-mono font-bold text-rose-300">timeout_ms</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">int</td>
              <td className="py-3.5 px-4 font-mono text-slate-400">None</td>
              <td className="py-3.5 px-4 text-slate-300">Automatically abort requests that take longer than this duration.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
