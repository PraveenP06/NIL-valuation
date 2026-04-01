import { cn } from "@/lib/utils";

type Props = {
  label: string;
  value: string | number;
  subLabel?: string;
  highlight?: boolean;
};

export function StatCard({ label, value, subLabel, highlight = false }: Props) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 flex flex-col gap-1 relative overflow-hidden",
        highlight && "border-primary/30"
      )}
    >
      {highlight && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-primary/60 via-primary to-primary/60" />
      )}
      <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium">{label}</p>
      <p className={cn(
        "text-2xl font-display font-bold tabular-nums",
        highlight && "text-primary gold-glow"
      )}>
        {value}
      </p>
      {subLabel && <p className="text-xs text-muted-foreground">{subLabel}</p>}
    </div>
  );
}
