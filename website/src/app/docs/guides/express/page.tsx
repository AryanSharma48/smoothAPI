import CodeBlock from "@/components/CodeBlock";

export default function ExpressGuidePage() {
  const code = `import express from 'express';
import { createSmoothFetch } from '@codingaryan/smoothapi';

const app = express();

// 1. Initialize SmoothAPI outside the route handler.
// This maintains the circuit state across all incoming requests.
const smoothFetch = createSmoothFetch({
  backoff: {
    baseDelay: 200,
    maxRetries: 4
  },
  circuitBreaker: {
    failureThreshold: 5, 
    cooldownMs: 30000 // 30 second cooldown
  },
  fallback: { message: "The database is currently overloaded, please try again later." },
  deduplication: { enabled: true }
});

// 2. Use it inside your route handlers
app.get('/api/users', async (req, res) => {
  try {
    const upstreamRes = await smoothFetch('https://internal-microservice/users');
    const data = await upstreamRes.json();
    
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: "Internal Server Error" });
  }
});

app.listen(3000, () => {
  console.log('Server is running on port 3000');
});`;

  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">Express.js Integration Guide</h2>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        Integrating SmoothAPI into an Express application is straightforward. The most important rule is to <strong>instantiate your self-healing fetch function outside of your request handlers</strong>.
      </p>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        If you instantiate it inside the route, a new Circuit Breaker is created for every incoming request, completely defeating the purpose of the state machine!
      </p>

      <h3 className="text-2xl font-bold mt-8 mb-4">Example Integration</h3>
      <CodeBlock language="typescript" code={code} />
    </div>
  );
}
