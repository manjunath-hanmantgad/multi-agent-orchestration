import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: "Multi-Agent Orchestration Platform",
  description: "Enterprise workflow orchestration with human-in-the-loop approval.",
};

const navItems = [
  { label: "Dashboard", href: "/" },
  { label: "Workflows", href: "/" },
  { label: "Triage", href: "/" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex font-sans">
        <aside className="w-56 shrink-0 border-r border-border bg-card flex flex-col">
          <div className="p-4 border-b border-border">
            <Link href="/" className="text-sm font-semibold text-foreground">
              Orchestrator
            </Link>
          </div>
          <nav className="flex-1 p-2 space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className="block px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>

        <main className="flex-1 flex flex-col min-w-0">
          {children}
        </main>

        <Toaster />
      </body>
    </html>
  );
}
