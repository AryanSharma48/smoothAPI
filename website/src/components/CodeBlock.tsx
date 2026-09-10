"use client";
import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

interface CodeBlockProps {
  language: string;
  code: string;
}

export default function CodeBlock({ language, code }: CodeBlockProps) {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy text: ", err);
    }
  };

  return (
    <div className="relative rounded-xl overflow-hidden border border-slate-800 bg-[#070a13] shadow-md my-4 text-sm font-mono leading-relaxed group">
      <div className="absolute right-3 top-3 z-10 flex items-center space-x-2">
        {isCopied && (
          <span className="text-xs text-rose-400 font-sans font-medium bg-rose-500/10 px-2 py-1 rounded-md animate-pulse">
            Copied to clipboard!
          </span>
        )}
        <button
          onClick={handleCopy}
          className="p-1.5 rounded-md bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors border border-slate-700 shadow-sm cursor-pointer"
          aria-label="Copy code"
        >
          {isCopied ? (
            <svg className="w-4 h-4 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          )}
        </button>
      </div>
      <SyntaxHighlighter 
        language={language} 
        style={vscDarkPlus} 
        customStyle={{ margin: 0, background: 'transparent', padding: '1.25rem', paddingTop: '2.5rem' }}
        wrapLongLines={true}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
