"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Leaderboard", icon: TrendingUp },
  { href: "/search", label: "Search", icon: Search },
];

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="container flex h-16 items-center gap-6">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 shrink-0">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-primary text-primary-foreground font-display font-bold text-sm">
            NIL
          </div>
          <div className="flex flex-col leading-none">
            <span className="font-display font-semibold text-base tracking-wide text-foreground">
              CFB Valuations
            </span>
            <span className="text-[10px] text-muted-foreground tracking-widest uppercase">
              Model · 2025 Season
            </span>
          </div>
        </Link>

        {/* Nav */}
        <nav className="flex items-center gap-1 ml-auto">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
