"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
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
    <div className="rounded-xl border bg-card overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-6 py-4 text-sm font-medium hover:bg-muted/50 transition-colors"
      >
        <span>Public Valuations ({entries.length} source{entries.length !== 1 ? "s" : ""})</span>
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>

      {open && (
        <div className="border-t">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-6 py-2 text-left text-muted-foreground font-medium">Source</th>
                <th className="px-6 py-2 text-right text-muted-foreground font-medium">Value</th>
                <th className="px-6 py-2 text-right text-muted-foreground font-medium hidden sm:table-cell">Date</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} className="border-t">
                  <td className="px-6 py-2">{formatSourceLabel(e.source)}</td>
                  <td className="px-6 py-2 text-right font-mono font-medium">{formatNilValue(e.nil_value)}</td>
                  <td className="px-6 py-2 text-right text-muted-foreground hidden sm:table-cell">
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
