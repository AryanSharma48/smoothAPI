export default function IntroductionPage() {
  return (
    <div>
      <h1 className="text-4xl font-extrabold tracking-tight mb-6">Introduction</h1>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        A failing third-party API can bring down your entire application, leading to cascading service failures, degraded user experience, and lost revenue. How do you protect your systems and keep them self-healing, even when downstream dependencies are completely unresponsive or failing?
      </p>
      <p className="text-slate-300 leading-7 text-lg mb-6">
        Enter <strong>SmoothAPI</strong>. SmoothAPI stops third-party API crashes from breaking your app. It wraps your HTTP calls with industry-standard self-healing patterns, catches network errors instantly, spaces out retries so recovering servers can breathe, and serves safe backup data the millisecond a service goes completely dead.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
        <div className="border border-slate-800 bg-slate-900/30 p-5 rounded-xl">
          <h3 className="font-bold text-rose-400 mb-2">TypeScript Native</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Dual-environment fetch wrapper supporting Edge, Serverless, and Node.js with built-in type inference.
          </p>
        </div>
        <div className="border border-slate-800 bg-slate-900/30 p-5 rounded-xl">
          <h3 className="font-bold text-rose-400 mb-2">Python Native</h3>
          <p className="text-slate-400 text-sm leading-relaxed">
            Elegant function decorator supporting both sync and async functions, integrating smoothly with requests and httpx.
          </p>
        </div>
      </div>
    </div>
  );
}
