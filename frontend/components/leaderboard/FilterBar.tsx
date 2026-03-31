"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { classYearLabel } from "@/lib/format";
import type { FilterMeta, ValuationFilters } from "@/lib/types";

type Props = {
  filters: ValuationFilters;
  onFiltersChange: (next: ValuationFilters) => void;
  meta: FilterMeta | undefined;
  isLoading: boolean;
};

const SEASONS = [2025, 2024];
const CLASS_YEARS = [1, 2, 3, 4];

export function FilterBar({ filters, onFiltersChange, meta, isLoading }: Props) {
  const update = (key: keyof ValuationFilters, raw: string) => {
    const value = raw === "all" ? null : key === "class_year" ? Number(raw) : raw;
    onFiltersChange({ ...filters, [key]: value, offset: 0 });
  };

  return (
    <div className="grid grid-cols-2 md:flex md:flex-row gap-2">
      {/* Season */}
      <Select
        value={String(filters.season)}
        onValueChange={(v) => onFiltersChange({ ...filters, season: Number(v), offset: 0 })}
        disabled={isLoading}
      >
        <SelectTrigger className="w-full md:w-32">
          <SelectValue placeholder="Season" />
        </SelectTrigger>
        <SelectContent>
          {SEASONS.map((s) => (
            <SelectItem key={s} value={String(s)}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Position */}
      <Select
        value={filters.position ?? "all"}
        onValueChange={(v) => update("position", v)}
        disabled={isLoading}
      >
        <SelectTrigger className="w-full md:w-36">
          <SelectValue placeholder="Position" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Positions</SelectItem>
          {meta?.positions.map((p) => (
            <SelectItem key={p} value={p}>
              {p}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Conference */}
      <Select
        value={filters.conference ?? "all"}
        onValueChange={(v) => update("conference", v)}
        disabled={isLoading}
      >
        <SelectTrigger className="w-full md:w-40">
          <SelectValue placeholder="Conference" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Conferences</SelectItem>
          {meta?.conferences.map((c) => (
            <SelectItem key={c} value={c}>
              {c}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Class Year */}
      <Select
        value={filters.class_year != null ? String(filters.class_year) : "all"}
        onValueChange={(v) => update("class_year", v)}
        disabled={isLoading}
      >
        <SelectTrigger className="w-full md:w-32">
          <SelectValue placeholder="Class" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Classes</SelectItem>
          {CLASS_YEARS.map((y) => (
            <SelectItem key={y} value={String(y)}>
              {classYearLabel(y)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
