import { Progress } from "@/components/ui/progress";
import { scoreLabel, formatScore } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PlayerValuation } from "@/lib/types";

const SCORE_KEYS = [
  "perf_score",
  "social_score",
  "school_score",
  "class_score",
  "recruit_score",
  "collective_score",
] as const;

type ScoreKey = (typeof SCORE_KEYS)[number];

function scoreColor(value: number): string {
  if (value >= 70) return "bg-emerald-500";
  if (value >= 40) return "bg-amber-500";
  return "bg-rose-500";
}

type Props = {
  valuation: Pick<PlayerValuation, ScoreKey>;
};

export function ScoreBreakdownChart({ valuation }: Props) {
  return (
    <div className="rounded-xl border bg-card p-6 space-y-4">
      <h3 className="font-semibold text-base">Score Breakdown</h3>
      <div className="space-y-3">
        {SCORE_KEYS.map((key) => {
          const raw = valuation[key];
          const value = raw ?? 0;
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="w-28 text-sm text-muted-foreground shrink-0">
                {scoreLabel(key)}
              </span>
              <Progress
                value={value}
                className="flex-1 h-2.5"
                indicatorClassName={cn(scoreColor(value))}
              />
              <span className="w-8 text-right text-sm font-mono font-medium">
                {formatScore(raw)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
