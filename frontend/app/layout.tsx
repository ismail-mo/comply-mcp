import type { Metadata } from 'next';
import type React from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'COMPLY',
  description: 'Engineering compliance checker',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-background text-primary font-mono antialiased">
        {children}
      </body>
    </html>
  );
}
