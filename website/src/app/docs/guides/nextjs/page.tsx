import CodeBlock from "@/components/CodeBlock";

export default function NextjsGuidePage() {
  const code = `import { NextResponse } from 'next/server';
import { createSmoothFetch } from '@codingaryan/smoothapi';

// Create the fetch instance outside the route handler
// so the Circuit Breaker state is preserved across requests!
const smoothFetch = createSmoothFetch({
  backoff: { maxRetries: 3, baseDelay: 100 },
  circuitBreaker: { failureThreshold: 3, cooldownMs: 10000 },
  fallback: { status: "degraded", error: "Upstream service is down." },
  timeoutMs: 2000,
});

export async function GET() {
  // Use cache: 'no-store' to ensure we hit the actual network
  // and bypass Next.js static caching.
  const res = await smoothFetch('https://api.example.com/unstable', {
    cache: 'no-store' 
  });
  
  const data = await res.json();
  return NextResponse.json(data);
}`;

  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">Next.js Integration Guide</h2>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        When using SmoothAPI with Next.js, especially the App Router (\`app/\`), there are a few important considerations regarding the built-in \`fetch\` cache.
      </p>

      <h3 className="text-2xl font-bold mt-8 mb-4">Bypassing the Next.js Cache</h3>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        By default, Next.js aggressively caches \`fetch\` requests. When using SmoothAPI&apos;s circuit breaker and retry mechanisms, you usually want the requests to be executed dynamically to accurately track the upstream health.
      </p>

      <h4 className="text-xl font-bold mt-6 mb-3">Example: Route Handler</h4>
      <CodeBlock language="typescript" code={code} />

      <h3 className="text-2xl font-bold mt-8 mb-4">Client Components vs Server Components</h3>
      <ul className="list-disc pl-6 text-slate-300 space-y-2">
        <li>
          <strong>Server Components:</strong> Initialize \`createSmoothFetch\` at the module level (outside the component) to maintain the state machine.
        </li>
        <li>
          <strong>Client Components:</strong> You can use \`createSmoothFetch\` securely in the browser, and the circuit breaker state will be maintained per-user for the duration of their session.
        </li>
      </ul>
    </div>
  );
}
