"use client";
import React, { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { navLinks } from "./Sidebar";

export default function Header() {
  const [githubStars, setGithubStars] = useState<number | null>(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const pathname = usePathname();

  // Close menu on route change
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [pathname]);

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
    <header className="sticky top-0 z-[100] border-b border-slate-800 bg-[#0b0f19]/80 backdrop-blur-md">
      <div className="flex items-center justify-between px-6 py-5 md:px-8">
        <div className="flex items-center space-x-3 cursor-pointer">
          <button 
            className="lg:hidden p-2 -ml-2 text-slate-300 hover:text-white rounded-md hover:bg-slate-800 transition-colors"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label="Toggle Menu"
          >
            {isMobileMenuOpen ? (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
          <Link href="/">
            <Image src="/logo.svg" alt="SmoothAPI Logo" width={220} height={48} priority className="h-9 md:h-10 w-auto" />
          </Link>
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
    </div>
      {/* Mobile Navigation Backdrop */}
      <div 
        className={`lg:hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-[110] transition-opacity duration-300 ${
          isMobileMenuOpen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        onClick={() => setIsMobileMenuOpen(false)}
      />

      {/* Mobile Navigation Drawer */}
      <div 
        className={`lg:hidden fixed inset-y-0 left-0 w-72 bg-[#0b0f19] border-r border-slate-800 p-6 overflow-y-auto z-[120] transform transition-transform duration-300 ease-in-out ${
          isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between mb-8">
          <Link href="/" onClick={() => setIsMobileMenuOpen(false)}>
            <Image src="/logo.svg" alt="SmoothAPI Logo" width={180} height={40} priority className="h-8 w-auto" />
          </Link>
          <button 
            className="p-2 -mr-2 text-slate-400 hover:text-white rounded-md hover:bg-slate-800 transition-colors"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-label="Close Menu"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-8 pb-10">
          {navLinks.map((group) => (
            <div key={group.title}>
              <h4 className="text-xs uppercase font-mono tracking-widest text-slate-500 mb-4">{group.title}</h4>
              <ul className="space-y-3 font-medium text-base">
                {group.links.map((link) => {
                  const isActive = pathname === link.href;
                  return (
                    <li key={link.href}>
                      <Link
                        href={link.href}
                        className={`block text-left w-full transition-colors p-2 -mx-2 rounded-md ${
                          isActive
                            ? "bg-rose-500/10 text-rose-500 font-bold"
                            : "text-slate-300 hover:text-white hover:bg-slate-800/50"
                        }`}
                      >
                        {link.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </header>
  );
}
