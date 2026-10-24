import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "cachekit — Prompt cache analysis",
  description: "Find what breaks prompt-cache reuse, verify a fix, and measure the difference.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="site-header">
          <Link href="/" className="wordmark" aria-label="cachekit home">
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
              <path d="M3 5h18M3 12h12M3 19h6" fill="none" stroke="currentColor" strokeWidth="3" />
            </svg>
            cachekit
          </Link>
          <nav aria-label="Main navigation">
            <Link href="/">Workspace</Link>
            <Link href="/bench">Benchmarks</Link>
            <Link href="/fix">Fix status</Link>
            <Link href="/how-it-works">Method &amp; limitations</Link>
          </nav>
        </header>
        <main id="main" className="workspace">{children}</main>
        <footer className="site-footer">Analyze locally. Review the fix. Measure the result.</footer>
      </body>
    </html>
  );
}
