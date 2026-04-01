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

const SCORE_ICONS: Record<ScoreKey, string> = {
  perf_score:       "⚡",
  social_score:     "📱",
  school_score:     "🏛️",
  class_score:      "📅",
  recruit_score:    "⭐",
  collective_score: "💰",
};

const SCORE_DESC: Record<ScoreKey, string> = {
  perf_score:       "On-field production & efficiency",
  social_score:     "Social media following & reach",
  school_score:     "Program prestige & TV exposure",
  class_score:      "Years of eligibility remaining",
  recruit_score:    "High school recruiting rating",
  collective_score: "School NIL collective value",
};

function scoreBarColor(value: number): string {
  if (value >= 70) return "bg-emerald-500";
  if (value >= 40) return "bg-amber-500";
  return "bg-rose-500";
}

function scoreTier(value: number): { label: string; color: string } {
  if (value >= 80) return { label: "Elite", color: "text-emerald-400" };
  if (value >= 60) return { label: "Strong", color: "text-emerald-500" };
  if (value >= 40) return { label: "Average", color: "text-amber-400" };
  if (value >= 20) return { label: "Below Avg", color: "text-rose-400" };
  return { label: "Low", color: "text-rose-500" };
}

type Props = {
  valuation: Pick<PlayerValuation, ScoreKey>;
};

export function ScoreBreakdownChart({ valuation }: Props) {
  return (
    <div className="rounded-xl border border-border/80 bg-card p-6 space-y-5 card-glow">
      <div>
        <h3 className="font-display font-semibold text-lg tracking-wide">Score Breakdown</h3>
        <p className="text-xs text-muted-foreground mt-0.5">Six factors that drive the model valuation</p>
      </div>

      <div className="space-y-4">
        {SCORE_KEYS.map((key) => {
          const raw = valuation[key];
          const value = raw ?? 0;
          const tier = scoreTier(value);

          return (
            <div key={key} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-base">{SCORE_ICONS[key]}</span>
                  <div>
                    <span className="text-sm font-medium text-foreground">{scoreLabel(key)}</span>
                    <span className="hidden sm:inline text-xs text-muted-foreground ml-2">{SCORE_DESC[key]}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={cn("text-xs font-medium hidden sm:inline", tier.color)}>{tier.label}</span>
                  <span className="text-sm font-mono font-bold text-foreground tabular-nums w-8 text-right">
                    {formatScore(raw)}
                  </span>
                </div>
              </div>
              <Progress
                value={value}
                className="h-2 bg-muted/60"
                indicatorClassName={cn(scoreBarColor(value), "transition-all duration-500")}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
