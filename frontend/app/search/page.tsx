import type { Metadata } from "next";
import { SearchContainer } from "@/components/search/SearchContainer";

export const metadata: Metadata = {
  title: "Search Players | CFB NIL Valuation",
  description: "Search for any college football player and view their NIL valuation.",
};

export default function SearchPage() {
  return (
    <div className="container py-8 max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">Search Players</h1>
      <SearchContainer />
    </div>
  );
}
