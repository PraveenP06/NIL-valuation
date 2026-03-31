import Link from "next/link";
import { Search } from "lucide-react";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center gap-6">
        <Link href="/" className="flex items-center gap-2 font-bold text-lg">
          <span className="text-primary">NIL</span>
          <span className="text-muted-foreground font-normal">Valuations</span>
        </Link>
        <nav className="flex items-center gap-4 ml-auto text-sm">
          <Link
            href="/"
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            Leaderboard
          </Link>
          <Link
            href="/search"
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
          >
            <Search className="h-4 w-4" />
            Search
          </Link>
        </nav>
      </div>
    </header>
  );
}
