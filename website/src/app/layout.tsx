import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

const sansFont = Plus_Jakarta_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SmoothAPI",
  description: "Zero-dependency, dual-language API resilience and fault-tolerance library. Implemented natively in TypeScript and Python with exponential backoff and circuit breaking.",
  icons: {
    icon: "/icon.svg",
  }
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${sansFont.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans selection:bg-rose-500/30 selection:text-rose-200">
        {children}
      </body>
    </html>
  );
}
