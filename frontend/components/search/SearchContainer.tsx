"use client";

import { useState, useEffect } from "react";
import { useSearch } from "@/hooks/useSearch";
import { SearchInput } from "./SearchInput";
import { SearchResultCard } from "./SearchResultCard";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorMessage } from "@/components/shared/ErrorMessage";

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function SearchContainer() {
  const [rawQuery, setRawQuery] = useState("");
  const debouncedQuery = useDebounce(rawQuery, 300);

  const { data, isLoading, isError, error, refetch } = useSearch(debouncedQuery, 2025);
  const players = data?.data ?? [];

  return (
    <div className="space-y-4">
      <SearchInput
        value={rawQuery}
        onChange={setRawQuery}
        isLoading={isLoading && debouncedQuery.length >= 2}
      />

      {debouncedQuery.length < 2 ? (
        <EmptyState
          title="Search for any CFB player"
          description="Type at least 2 characters to find a player by name."
        />
      ) : isError ? (
        <ErrorMessage
          message={(error as Error)?.message ?? "Search failed"}
          onRetry={() => refetch()}
        />
      ) : isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      ) : players.length === 0 ? (
        <EmptyState
          title={`No results for "${debouncedQuery}"`}
          description="Try a different name or spelling."
        />
      ) : (
        <div className="space-y-2">
          {players.map((player) => (
            <SearchResultCard key={player.id} player={player} />
          ))}
        </div>
      )}
    </div>
  );
}
