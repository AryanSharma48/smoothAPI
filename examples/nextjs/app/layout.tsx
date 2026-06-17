import type { ReactNode } from 'react';

export const metadata = {
  title: 'smoothapi Next.js example',
  description: 'Resilient fetch demo against the chaos sandbox',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
