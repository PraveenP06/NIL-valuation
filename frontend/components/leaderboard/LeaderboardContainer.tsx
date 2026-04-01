"use client";

import { useState } from "react";
import { useValuations } from "@/hooks/useValuations";
import { useFilterMeta } from "@/hooks/useFilterMeta";
import { useStats } from "@/hooks/useStats";
import { FilterBar } from "./FilterBar";
import { PlayerTable } from "./PlayerTable";
import { LeaderboardSkeleton } from "./LeaderboardSkeleton";
import { StatCard } from "@/components/shared/StatCard";
import { ErrorMessage } from "@/components/shared/ErrorMessage";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { formatNilValue } from "@/lib/format";
import type { ValuationFilters } from "@/lib/types";

const DEFAULT_FILTERS: ValuationFilters = {
  season: 2025,
  position: null,
  conference: null,
  class_year: null,
  limit: 50,
  offset: 0,
};

export function LeaderboardContainer() {
  const [filters, setFilters] = useState<ValuationFilters>(DEFAULT_FILTERS);

  const { data, isLoading, isError, error, refetch } = useValuations(filters);
  const { data: meta, isLoading: metaLoading } = useFilterMeta(filters.season);
  const { data: stats } = useStats(filters.season);

  const players = data?.data ?? [];
  const hasMore = players.length === filters.limit;

  return (
    <div className="container py-8 space-y-8">
      {/* Hero */}
      <div className="space-y-1">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-4xl font-bold tracking-wide text-foreground">
            NIL <span className="text-primary gold-glow">Leaderboard</span>
          </h1>
          <span className="rounded border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
            2025 Season
          </span>
        </div>
        <p className="text-muted-foreground text-sm max-w-xl">
          Model-driven NIL valuations for college football players. Factors include performance, social following, school prestige, recruiting pedigree, and collective value.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Players"
          value={stats?.players_count?.toLocaleString() ?? "—"}
          subLabel="in database"
        />
        <StatCard
          label="Valuations"
          value={stats?.valuations_count?.toLocaleString() ?? "—"}
          subLabel={`${filters.season} season`}
        />
        <StatCard
          label="Top NIL Value"
          value={formatNilValue(stats?.top_nil_value ?? null)}
          subLabel="this season"
          highlight
        />
        <StatCard
          label="With Social Data"
          value={stats?.social_data_count?.toLocaleString() ?? "—"}
          subLabel="players tracked"
        />
      </div>

      {/* Filters */}
      <FilterBar
        filters={filters}
        onFiltersChange={setFilters}
        meta={meta}
        isLoading={metaLoading}
      />

      {/* Table */}
      {isError ? (
        <ErrorMessage
          message={(error as Error)?.message ?? "Failed to load players"}
          onRetry={() => refetch()}
        />
      ) : isLoading ? (
        <LeaderboardSkeleton rows={15} />
      ) : players.length === 0 ? (
        <EmptyState
          title="No players found"
          description="Try adjusting your filters."
        />
      ) : (
        <>
          <PlayerTable players={players} offset={filters.offset} />

          {/* Pagination */}
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Showing {filters.offset + 1}–{filters.offset + players.length}
            </span>
            <div className="flex gap-2">
              {filters.offset > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setFilters((f) => ({
                      ...f,
                      offset: Math.max(0, f.offset - f.limit),
                    }))
                  }
                >
                  Previous
                </Button>
              )}
              {hasMore && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setFilters((f) => ({ ...f, offset: f.offset + f.limit }))
                  }
                >
                  Next
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
