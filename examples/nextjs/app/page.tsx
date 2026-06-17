'use client';

import { useState } from 'react';

export default function Home() {
  const [output, setOutput] = useState<string>('Click a button to call a route.');

  async function call(path: string) {
    setOutput('Loading...');
    try {
      const res = await fetch(path);
      const json = await res.json();
      setOutput(JSON.stringify(json, null, 2));
    } catch (err) {
      setOutput(`Request failed: ${String(err)}`);
    }
  }

  return (
    <main style={{ fontFamily: 'monospace', padding: 24 }}>
      <h1>smoothapi Next.js example</h1>
      <p>Make sure the sandbox server is running on http://localhost:3001.</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => call('/api/resilient')}>Call /api/resilient</button>
        <button onClick={() => call('/api/circuit-demo')}>Call /api/circuit-demo</button>
      </div>
      <pre style={{ marginTop: 16, padding: 12, background: '#f0f0f0' }}>{output}</pre>
    </main>
  );
}
