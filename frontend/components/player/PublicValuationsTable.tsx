"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { formatNilValue, formatSourceLabel } from "@/lib/format";
import type { PublicValuationEntry } from "@/lib/types";

type Props = {
  entries: PublicValuationEntry[];
};

const dateFmt = new Intl.DateTimeFormat("en-US", { dateStyle: "medium" });

export function PublicValuationsTable({ entries }: Props) {
  const [open, setOpen] = useState(false);

  if (entries.length === 0) return null;

  return (
    <div className="rounded-xl border border-border/80 bg-card overflow-hidden card-glow">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-accent/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <ExternalLink className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">
            Public Valuations
          </span>
          <span className="rounded-full bg-primary/15 text-primary text-xs font-medium px-2 py-0.5">
            {entries.length}
          </span>
        </div>
        {open
          ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
          : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </button>

      {open && (
        <div className="border-t border-border/60">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted/30">
                <th className="px-6 py-2.5 text-left text-xs text-muted-foreground font-medium uppercase tracking-wider">Source</th>
                <th className="px-6 py-2.5 text-right text-xs text-muted-foreground font-medium uppercase tracking-wider">Value</th>
                <th className="px-6 py-2.5 text-right text-xs text-muted-foreground font-medium uppercase tracking-wider hidden sm:table-cell">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {entries.map((e, i) => (
                <tr key={i} className="hover:bg-accent/30 transition-colors">
                  <td className="px-6 py-3 text-muted-foreground">{formatSourceLabel(e.source)}</td>
                  <td className="px-6 py-3 text-right font-mono font-semibold text-amber-400 tabular-nums">
                    {formatNilValue(e.nil_value)}
                  </td>
                  <td className="px-6 py-3 text-right text-xs text-muted-foreground hidden sm:table-cell">
                    {dateFmt.format(new Date(e.scraped_at))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
