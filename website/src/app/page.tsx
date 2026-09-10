"use client";
import React, { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import Footer from "@/components/Footer";

export default function LandingPage() {
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

  return (
    <div className="min-h-screen flex flex-col bg-[#0b0f19] text-slate-100 selection:bg-rose-500/30 selection:text-rose-200">
      <main className="flex-1 flex flex-col items-center justify-center py-20 px-6 text-center">
        <div className="mb-8">
          <Image src="/logo.svg" alt="SmoothAPI Logo" width={400} height={100} priority className="h-20 w-auto mx-auto" />
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-6 max-w-3xl">
          Zero-dependency, dual-language API self-healing and fault-tolerance.
        </h1>
        <p className="text-slate-300 leading-relaxed text-lg md:text-xl mb-12 max-w-2xl mx-auto">
          SmoothAPI stops third-party API crashes from breaking your app. It wraps your HTTP calls with industry-standard self-healing patterns, catches network errors instantly, and serves safe backup data.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 items-stretch sm:items-center justify-center w-full max-w-md mx-auto sm:max-w-none">
          <Link href="/docs/introduction" className="flex items-center justify-center bg-rose-500 hover:bg-rose-600 text-white font-bold py-4 px-8 rounded-full transition-colors text-base md:text-lg shadow-lg shadow-rose-500/20 w-full sm:w-auto text-center">
            Read the Documentation
          </Link>
          <a href="https://github.com/AryanSharma48/smoothAPI" target="_blank" rel="noreferrer" className="flex items-center justify-center bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-100 font-bold py-4 px-8 rounded-full transition-colors text-base md:text-lg w-full sm:w-auto text-center">
            View on GitHub
            {githubStars !== null && (
              <span className="flex items-center pl-3 ml-3 border-l border-slate-600 font-mono text-sm">
                <svg className="w-5 h-5 mr-1 text-yellow-400 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
                </svg>
                {githubStars.toLocaleString()}
              </span>
            )}
          </a>
        </div>
      </main>
      <Footer />
    </div>
  );
}
