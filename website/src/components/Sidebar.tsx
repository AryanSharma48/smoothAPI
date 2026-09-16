"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export const navLinks = [
  { title: "Getting Started", links: [
      { href: "/docs/introduction", label: "Introduction" },
      { href: "/docs/installation", label: "Installation" },
      { href: "/docs/quickstart", label: "Quickstart" },
  ]},
  { title: "Core Concepts", links: [
      { href: "/docs/features", label: "Core Features" },
      { href: "/docs/configuration", label: "Configuration" },
  ]},
  { title: "Framework Guides", links: [
      { href: "/docs/guides/nextjs", label: "Next.js" },
      { href: "/docs/guides/express", label: "Express.js" },
      { href: "/docs/guides/fastapi", label: "FastAPI" },
  ]},
  { title: "API Reference", links: [
      { href: "/docs/api/typescript", label: "TypeScript SDK" },
      { href: "/docs/api/python", label: "Python SDK" },
  ]},
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="w-64 border-r border-slate-800/80 p-6 hidden lg:block sticky top-16 h-[calc(100vh-4rem)]">
      <div className="space-y-8">
        {navLinks.map((group) => (
          <div key={group.title}>
            <h4 className="text-xs uppercase font-mono tracking-widest text-slate-500 mb-4">{group.title}</h4>
            <ul className="space-y-3 font-medium text-sm">
              {group.links.map((link) => {
                const isActive = pathname === link.href;
                return (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className={`block text-left w-full transition-colors ${
                        isActive
                          ? "text-rose-500 font-bold"
                          : "text-slate-400 hover:text-slate-200"
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
    </nav>
  );
}
