import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";

import { AppShell } from "@/components/app-shell/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Targeted File Review",
  description: "Agent-assisted audit form review, evaluation, and optimization.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <AppShell>{children}</AppShell>
        <noscript>
          <div className="fixed inset-x-0 bottom-0 bg-destructive p-3 text-center text-sm text-destructive-foreground">
            JavaScript is required for the TFR application shell.{" "}
            <Link href="/">Return home</Link>
          </div>
        </noscript>
      </body>
    </html>
  );
}
