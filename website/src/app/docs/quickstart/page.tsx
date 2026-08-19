"use client";
import React, { useState } from "react";
import CodeBlock from "@/components/CodeBlock";

export default function QuickstartPage() {
  const [codeLang, setCodeLang] = useState<"ts" | "py">("ts");

  const tsCode = `import { createSmoothFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createSmoothFetch({
  backoff: {
    baseDelay: 100,      // ms
    maxRetries: 3        // retry 3 times
  },
  circuitBreaker: {
    failureThreshold: 3, // trip OPEN after 3 consecutive errors
    cooldownMs: 10000    // stay OPEN for 10 seconds
  },
  fallback: { status: "degraded", data: [] }
});

// Use it just like normal fetch!
const response = await fetchWithRetry('https://api.example.com/unstable');`;

  const pyCode = `import requests
from smooth_api import smooth_api, SmoothConfig

config = SmoothConfig(
    fallback={"status": "degraded", "data": []},
    fallback_on_non_retryable=True
)

@smooth_api(config)
def get_data():
    res = requests.get('https://api.example.com/unstable')
    res.raise_for_status() # Raise exception so decorator can intercept!
    return res.json()

# Execute safely
data = get_data()`;

  return (
    <div>
      <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-6">
        <h2 className="text-3xl font-bold">Quickstart Guide</h2>
        <div className="flex bg-slate-900 border border-slate-800 p-0.5 rounded-lg text-xs font-mono font-bold">
          <button
            onClick={() => setCodeLang("ts")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              codeLang === "ts" ? "bg-rose-500 text-white shadow" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            TypeScript
          </button>
          <button
            onClick={() => setCodeLang("py")}
            className={`px-3 py-1.5 rounded-md transition-all ${
              codeLang === "py" ? "bg-rose-500 text-white shadow" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Python
          </button>
        </div>
      </div>

      {codeLang === "ts" ? (
        <div className="space-y-4">
          <p className="text-slate-300 text-sm">
            Create a custom self-healing fetch instance and use it as a drop-in replacement for native \`fetch\`:
          </p>
          <CodeBlock language="typescript" code={tsCode} />
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-slate-300 text-sm">
            Wrap any request functions using the \`smooth_api\` decorator to catch exceptions and manage backoff:
          </p>
          <CodeBlock language="python" code={pyCode} />
        </div>
      )}
    </div>
  );
}
