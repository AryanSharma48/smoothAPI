import type { ReactNode } from 'react';

export const metadata = {
  title: 'Next.js App Router API Robustness Demo',
  description: 'Robust fetch demo against the chaos sandbox',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
