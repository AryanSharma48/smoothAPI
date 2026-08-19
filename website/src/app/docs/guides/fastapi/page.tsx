import CodeBlock from "@/components/CodeBlock";

export default function FastAPIGuidePage() {
  const code = `import httpx
from fastapi import FastAPI, HTTPException
from smooth_api import smooth_api, SmoothConfig

app = FastAPI()

# 1. Initialize configuration at the module level
config = SmoothConfig(
    fallback={"status": "degraded", "data": "Upstream is down. Using safe fallback data."},
    fallback_on_non_retryable=True,
    timeout_ms=3000
)

# 2. Wrap your async service function
@smooth_api(config)
async def fetch_upstream_data():
    async with httpx.AsyncClient() as client:
        # We simulate a call that might timeout or return 503
        response = await client.get("https://api.example.com/unstable")
        
        # httpx requires manually calling raise_for_status() 
        # so SmoothAPI can catch the Exception!
        response.raise_for_status()
        
        return response.json()

# 3. Use the self-healing function in your route
@app.get("/data")
async def get_data():
    try:
        data = await fetch_upstream_data()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Service Unavailable")`;

  return (
    <div>
      <h2 className="text-3xl font-bold mb-6">FastAPI Integration Guide</h2>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        Python&apos;s <code>asyncio</code> and web frameworks like FastAPI work beautifully with SmoothAPI. The <code>@smooth_api</code> decorator automatically detects if the function it is wrapping is <code>async</code> or sync and handles it accordingly.
      </p>

      <h3 className="text-2xl font-bold mt-8 mb-4">Async Integration Example</h3>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        Here is a simple example of using <code>httpx</code> and SmoothAPI inside a FastAPI application.
      </p>
      
      <CodeBlock language="python" code={code} />
    </div>
  );
}
