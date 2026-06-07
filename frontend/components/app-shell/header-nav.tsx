"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Database, FileCheck2, Files, Home, Moon, Rows3, Settings2, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Home", icon: Home },
  { href: "/batch-audits", label: "Batch Audits", icon: Rows3 },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/forms", label: "Forms", icon: Files },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/evaluation", label: "Evaluation", icon: FileCheck2 },
  { href: "/optimization", label: "Optimization", icon: Settings2 },
];

export function HeaderNav({
  theme,
  onToggleTheme,
}: {
  theme: "light" | "dark";
  onToggleTheme: () => void;
}) {
  const pathname = usePathname();

  return (
    <header className="fixed inset-x-0 top-0 z-40 h-14 border-b bg-background/95 backdrop-blur">
      <div className="flex h-full items-center gap-3 px-4">
        <Link href="/" className="flex min-w-fit items-center gap-2 font-semibold">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-sm text-primary-foreground">
            TFR
          </span>
          <span className="hidden sm:inline">Targeted File Review Assistant</span>
        </Link>

        <nav className="ml-2 flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Button key={item.href} asChild variant={active ? "secondary" : "ghost"} size="sm">
                <Link className={cn("gap-1.5", active && "text-foreground")} href={item.href}>
                  <Icon className="h-4 w-4" />
                  <span className="hidden md:inline">{item.label}</span>
                </Link>
              </Button>
            );
          })}
        </nav>

        <Button variant="ghost" size="icon" onClick={onToggleTheme} aria-label="Toggle theme" title="Toggle theme">
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
