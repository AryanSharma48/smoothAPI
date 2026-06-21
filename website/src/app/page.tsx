"use client";

import React, { useState, useEffect, useRef } from "react";
import Image from "next/image";

// Documentation sections type definition
type Section = {
  id: string;
  title: string;
};

const SECTIONS: Section[] = [
  { id: "introduction", title: "Introduction" },
  { id: "installation", title: "Installation" },
  { id: "quickstart", title: "Quickstart" },
  { id: "features", title: "Core Features" },
  { id: "simulator", title: "Interactive Simulator" },
  { id: "configuration", title: "Configuration Options" },
];

/*
// Simulator Logs Type
type SimLog = {
  time: string;
  type: "info" | "success" | "warning" | "error";
  text: string;
};
*/

export default function Home() {
  const [activeSection, setActiveSection] = useState("introduction");
  const [codeLang, setCodeLang] = useState<"ts" | "py">("ts");
  const [githubStars, setGithubStars] = useState<number | null>(null);

  useEffect(() => {
    fetch("https://api.github.com/repos/AryanSharma48/smoothAPI")
      .then((res) => res.json())
      .then((data) => {
        if (typeof data.stargazers_count === "number") {
          setGithubStars(data.stargazers_count);
        }
      })
      .catch((err) => console.error("Failed to fetch github stars:", err));
  }, []);

  /*
  // Simulator States
  const [circuitState, setCircuitState] = useState<"CLOSED" | "OPEN" | "HALF_OPEN">("CLOSED");
  const [failRate, setFailRate] = useState(0.8); // 80% failure when chaos injected
  const [injectChaos, setInjectChaos] = useState(false);
  const [failureCount, setFailureCount] = useState(0);
  const [simLogs, setSimLogs] = useState<SimLog[]>([]);
  const [isRequesting, setIsRequesting] = useState(false);
  const [successCount, setSuccessCount] = useState(0);
  */

  // Auto-scroll-spy ref array
  const sectionRefs = useRef<{ [key: string]: HTMLElement | null }>({});

  useEffect(() => {
    const handleScroll = () => {
      const scrollPosition = window.scrollY + 160;

      for (const section of SECTIONS) {
        const el = sectionRefs.current[section.id];
        if (el) {
          const top = el.offsetTop;
          const height = el.offsetHeight;
          if (scrollPosition >= top && scrollPosition < top + height) {
            setActiveSection(section.id);
            break;
          }
        }
      }
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollTo = (id: string) => {
    const el = sectionRefs.current[id];
    if (el) {
      const top = el.offsetTop - 80;
      window.scrollTo({ top, behavior: "smooth" });
      setActiveSection(id);
    }
  };

  /*
  // Add Log Helper
  const addLog = (text: string, type: "info" | "success" | "warning" | "error" = "info") => {
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setSimLogs((prev) => [{ time: now, type, text }, ...prev.slice(0, 19)]);
  };

  // Simulator Request Run
  const handleSimRequest = async () => {
    if (isRequesting) return;
    setIsRequesting(true);

    addLog(`Initiating API Request to /unstable-data...`, "info");

    // 1. Check Circuit Breaker State
    if (circuitState === "OPEN") {
      addLog(`[CircuitBreaker] BLOCKED: Circuit is OPEN. Serving Fallback immediately (No Network IO).`, "error");
      addLog(`Response: { status: "degraded", data: [] } (Fallback Served) ✅`, "success");
      setIsRequesting(false);
      return;
    }

    // Simulate Network request delay
    await new Promise((resolve) => setTimeout(resolve, 600));

    // Determine Success/Failure
    const isFailed = injectChaos ? Math.random() < failRate : false;

    if (isFailed) {
      // Failure Flow
      const nextFailCount = failureCount + 1;
      setFailureCount(nextFailCount);
      addLog(`API Call Failed: HTTP status 503 Service Unavailable`, "warning");

      if (circuitState === "HALF_OPEN") {
        setCircuitState("OPEN");
        setFailureCount(3);
        addLog(`[CircuitBreaker] Probe request failed. Tripping back to OPEN! Cooldown starts.`, "error");
      } else if (nextFailCount >= 3) {
        setCircuitState("OPEN");
        addLog(`[CircuitBreaker] 3 consecutive failures reached. Tripping to OPEN!`, "error");
      } else {
        addLog(`[CircuitBreaker] Failure recorded (${nextFailCount}/3). Preparing backoff retry...`, "info");
      }
    } else {
      // Success Flow
      setFailureCount(0);
      addLog(`API Call Succeeded: HTTP status 200 OK`, "success");

      if (circuitState === "HALF_OPEN") {
        setCircuitState("CLOSED");
        setSuccessCount(0);
        addLog(`[CircuitBreaker] Probe succeeded. Circuit is now CLOSED (Normal Operation).`, "success");
      } else {
        breakerSuccess();
      }
    }

    setIsRequesting(false);
  };

  const breakerSuccess = () => {
    if (circuitState === "CLOSED") return;
  };

  // Trigger Cooldown Recovery Simulation
  useEffect(() => {
    if (circuitState === "OPEN") {
      const timer = setTimeout(() => {
        setCircuitState("HALF_OPEN");
        addLog(`[CircuitBreaker] Cooldown expired. Transitioning to HALF_OPEN. Probing next request...`, "warning");
      }, 6000); // 6s simulator cooldown
      return () => clearTimeout(timer);
    }
  }, [circuitState]);

  const resetSimulator = () => {
    setCircuitState("CLOSED");
    setFailureCount(0);
    setInjectChaos(false);
    setSimLogs([]);
    addLog("Simulator reset. Circuit is CLOSED. Network operational.", "info");
  };
  */

  return (
    <div className="min-h-screen flex flex-col bg-[#0b0f19] text-slate-100 selection:bg-rose-500/30 selection:text-rose-200">
      
      {/* STICKY HEADER */}
      <header className="sticky top-0 z-50 flex items-center justify-between border-b border-slate-800 bg-[#0b0f19]/80 backdrop-blur-md px-8 py-5">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
          <Image src="/logo.svg" alt="SmoothAPI Logo" width={220} height={48} priority className="h-10 w-auto" />
        </div>
        <div className="flex items-center space-x-6">
          <span className="hidden sm:inline-block text-sm font-mono px-3 py-1.5 bg-slate-800 rounded-md text-slate-400 border border-slate-700">v{process.env.NEXT_PUBLIC_TS_PKG_VERSION || "1.0.0"}</span>
          <a href="https://github.com/AryanSharma48/smoothAPI" target="_blank" rel="noreferrer" className="flex items-center space-x-2 bg-slate-800/80 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white text-base font-medium px-4 py-2 rounded-md transition-colors shadow-sm">
            <svg className="w-6 h-6 fill-current" viewBox="0 0 24 24"><path d="M12 2A10 10 0 0 0 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.9 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z"/></svg>
            <span className="hidden sm:flex items-center">
              how about a star?
              <svg className="w-3.5 h-3.5 ml-1.5 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5l15-15m0 0H8.25m11.25 0v11.25" />
              </svg>
            </span>
            {githubStars !== null && (
              <span className="flex items-center pl-2 ml-1 border-l border-slate-600 font-mono font-bold text-sm">
                <svg className="w-4 h-4 mr-1 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
                </svg>
                {githubStars.toLocaleString()}
              </span>
            )}
          </a>
        </div>
      </header>

      <div className="flex flex-1 max-w-7xl w-full mx-auto">
        
        {/* LEFT NAVIGATION SIDEBAR */}
        <nav className="w-64 border-r border-slate-800/80 p-6 hidden lg:block sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto">
          <div className="space-y-8">
            <div>
              <h4 className="text-xs uppercase font-mono tracking-widest text-slate-500 mb-4">Documentation</h4>
              <ul className="space-y-3 font-medium text-sm">
                {SECTIONS.map((sec) => (
                  <li key={sec.id}>
                    <button
                      onClick={() => scrollTo(sec.id)}
                      className={`block text-left w-full transition-colors ${
                        activeSection === sec.id
                          ? "text-rose-500 font-bold"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {sec.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </nav>

        {/* MAIN DOCUMENTATION CONTENT */}
        <main className="flex-1 py-10 px-6 md:px-12 max-w-4xl overflow-y-auto">
          
          {/* INTRODUCTION */}
          <section
            id="introduction"
            ref={(el) => { sectionRefs.current["introduction"] = el; }}
            className="mb-16 scroll-mt-24"
          >
            <h1 className="text-4xl font-extrabold tracking-tight mb-6">Introduction</h1>
            <p className="text-slate-300 leading-7 text-lg mb-6">
              A failing third-party API can bring down your entire application, leading to cascading service failures, degraded user experience, and lost revenue. How do you protect your systems and keep them resilient, even when downstream dependencies are completely unresponsive or failing?
            </p>
            <p className="text-slate-300 leading-7 text-lg mb-6">
              Enter <strong>SmoothAPI</strong>. SmoothAPI stops third-party API crashes from breaking your app. It wraps your HTTP calls with industry-standard resilience patterns, catches network errors instantly, spaces out retries so recovering servers can breathe, and serves safe backup data the millisecond a service goes completely dead.
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
          </section>

          {/* INSTALLATION */}
          <section
            id="installation"
            ref={(el) => { sectionRefs.current["installation"] = el; }}
            className="mb-16 scroll-mt-24"
          >
            <h2 className="text-3xl font-bold mb-6">Installation</h2>
            <div className="space-y-6">
              <div>
                <h4 className="text-slate-300 font-semibold mb-2">TypeScript/JavaScript (NPM):</h4>
                <pre className="p-4 rounded-lg font-mono text-sm overflow-x-auto text-rose-300 select-all">
                  npm install @codingaryan/smoothapi
                </pre>
              </div>
              <div>
                <h4 className="text-slate-300 font-semibold mb-2">Python (PyPI):</h4>
                <pre className="p-4 rounded-lg font-mono text-sm overflow-x-auto text-rose-300 select-all">
                  pip install smoothapi-py
                </pre>
              </div>
            </div>
          </section>

          {/* QUICKSTART */}
          <section
            id="quickstart"
            ref={(el) => { sectionRefs.current["quickstart"] = el; }}
            className="mb-16 scroll-mt-24"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-6">
              <h2 className="text-3xl font-bold">Quickstart Guide</h2>
              {/* LANGUAGE TOGGLE */}
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
                  Create a custom resilient fetch instance and use it as a drop-in replacement for native `fetch`:
                </p>
                <pre className="p-5 rounded-xl font-mono text-xs text-slate-300 overflow-x-auto leading-relaxed">
{`import { createResilientFetch } from '@codingaryan/smoothapi';

const fetchWithRetry = createResilientFetch({
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
const response = await fetchWithRetry('https://api.example.com/unstable');`}
                </pre>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-slate-300 text-sm">
                  Wrap any request functions using the `resilient_api` decorator to catch exceptions and manage backoff:
                </p>
                <pre className="p-5 rounded-xl font-mono text-xs text-slate-300 overflow-x-auto leading-relaxed">
{`import requests
from smooth_api import resilient_api, ResilientConfig

config = ResilientConfig(
    fallback={"status": "degraded", "data": []},
    fallback_on_non_retryable=True
)

@resilient_api(config)
def get_data():
    res = requests.get('https://api.example.com/unstable')
    res.raise_for_status() # Raise exception so decorator can intercept!
    return res.json()

# Execute safely
data = get_data()`}
                </pre>
              </div>
            )}
          </section>

          {/* CORE FEATURES */}
          <section
            id="features"
            ref={(el) => { sectionRefs.current["features"] = el; }}
            className="mb-16 scroll-mt-24"
          >
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

            </div>
          </section>

          {/* INTERACTIVE SIMULATOR */}
          <section
            id="simulator"
            ref={(el) => { sectionRefs.current["simulator"] = el; }}
            className="mb-16 scroll-mt-24"
          >
            <h2 className="text-3xl font-bold mb-6">Interactive Simulator</h2>
            <p className="text-slate-300 mb-8">
              Test how the circuit breaker and fallback mechanisms work in real-time. Toggle network failures, dispatch requests, and monitor the circuit status well logs:
            </p>

            <div className="relative border border-slate-800 bg-[#0e1322]/40 backdrop-blur-sm rounded-2xl p-8 overflow-hidden text-center flex flex-col items-center justify-center min-h-[350px]">
              {/* Background gradient glow */}
              <div className="absolute -top-24 -left-24 w-48 h-48 bg-rose-500/5 rounded-full blur-3xl pointer-events-none" />
              <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-rose-500/5 rounded-full blur-3xl pointer-events-none" />
              
              {/* Animated Icon */}
              <div className="relative mb-6">
                <div className="absolute inset-0 bg-rose-500/20 rounded-full blur-xl scale-75 animate-pulse" />
                <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-slate-900 border border-slate-800 text-rose-500">
                  <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} style={{ animation: "spin 8s linear infinite" }}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065Z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z" />
                  </svg>
                </div>
              </div>

              {/* Status Badge */}
              <div className="text-yellow-400 font-mono font-bold tracking-widest text-sm mb-4 animate-pulse">
                COMING SOON
              </div>

              <h3 className="text-2xl font-bold text-slate-100 mb-3 tracking-tight">Interactive API Sandbox</h3>
              <p className="text-slate-400 text-sm max-w-md leading-relaxed mb-6">
                We are building a comprehensive real-time dashboard simulator. You will be able to inject customizable latency, simulate network timeouts, trigger random HTTP exceptions, and watch the circuit breaker dynamically transition states live.
              </p>

              {/* Simulated UI telemetry preview */}
              <div className="w-full max-w-sm bg-[#070a13]/60 border border-slate-800/80 rounded-xl p-4 text-left font-mono text-[11px] text-slate-500 select-none">
                <div className="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-2">
                  <span className="text-[10px] uppercase tracking-wider text-slate-600">Simulated Telemetry</span>
                  <span className="w-2 h-2 rounded-full bg-rose-500/40 animate-pulse" />
                </div>
                <div className="space-y-1.5">
                  <div>[10:42:01] <span className="text-slate-500">INFO</span> Initializing state machine...</div>
                  <div>[10:42:02] <span className="text-slate-500">INFO</span> Target endpoint: <span className="text-rose-500/60">api.smooth.dev/v1/chaos</span></div>
                  <div>[10:42:03] <span className="text-rose-500/70">WARN</span> Failure rate set to <span className="text-amber-500/70">80%</span>. Ready to probe.</div>
                </div>
              </div>
            </div>
          </section>

          {/* CONFIGURATION OPTIONS */}
          <section
            id="configuration"
            ref={(el) => { sectionRefs.current["configuration"] = el; }}
            className="mb-16 scroll-mt-24"
          >
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
                <tbody className="divide-y divide-slate-850">
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
                </tbody>
              </table>
            </div>
          </section>

        </main>

        {/* RIGHT SIDEBAR (TABLE OF CONTENTS) */}
        <aside className="w-60 p-6 hidden xl:block sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto border-l border-slate-800/50">
          <h4 className="text-xs uppercase font-mono tracking-widest text-slate-500 mb-4">On this page</h4>
          <ul className="space-y-3 font-medium text-xs">
            {SECTIONS.map((sec) => (
              <li key={sec.id}>
                <button
                  onClick={() => scrollTo(sec.id)}
                  className={`block text-left w-full hover:text-slate-200 transition-colors ${
                    activeSection === sec.id ? "text-rose-500 font-bold" : "text-slate-400"
                  }`}
                >
                  {sec.title}
                </button>
              </li>
            ))}
          </ul>
        </aside>

      </div>

      {/* FOOTER */}
      <footer className="border-t border-slate-800 py-8 px-6 bg-[#070a13]">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-slate-500 text-sm">
          <div>Released under the MIT License. &copy; 2026 Aryan Sharma.</div>
          <div className="flex space-x-6">
            <a href="https://www.npmjs.com/package/@codingaryan/smoothapi" target="_blank" rel="noreferrer" className="hover:text-rose-500 transition-colors">NPM Package</a>
            <a href="https://pypi.org/project/smoothapi-py/" target="_blank" rel="noreferrer" className="hover:text-rose-500 transition-colors">PyPI Package</a>
            <a href="https://github.com/AryanSharma48/smoothAPI" target="_blank" rel="noreferrer" className="hover:text-rose-500 transition-colors">GitHub</a>
          </div>
        </div>
      </footer>

    </div>
  );
}
