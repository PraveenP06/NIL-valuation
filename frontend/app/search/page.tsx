import type { Metadata } from "next";
import { SearchContainer } from "@/components/search/SearchContainer";

export const metadata: Metadata = {
  title: "Search Players | CFB NIL Valuation",
  description: "Search for any college football player and view their NIL valuation.",
};

export default function SearchPage() {
  return (
    <div className="container py-8 max-w-2xl">
      <div className="space-y-1 mb-6">
        <h1 className="font-display text-4xl font-bold tracking-wide">
          Player <span className="text-primary gold-glow">Search</span>
        </h1>
        <p className="text-sm text-muted-foreground">Find any CFB player and view their model NIL valuation.</p>
      </div>
      <SearchContainer />
    </div>
  );
}
