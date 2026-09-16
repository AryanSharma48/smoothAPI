import Header from "@/components/Header";
import Sidebar from "@/components/Sidebar";
import Footer from "@/components/Footer";
import React from "react";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#0b0f19] text-slate-100 selection:bg-rose-500/30 selection:text-rose-200">
      <Header />
      <div className="flex flex-1 max-w-7xl w-full mx-auto">
        <Sidebar />
        <main className="flex-1 py-10 px-6 md:px-12 max-w-4xl overflow-y-auto">
          {children}
        </main>
      </div>
      <Footer />
    </div>
  );
}
