type Props = {
  label: string;
  value: string | number;
  subLabel?: string;
};

export function StatCard({ label, value, subLabel }: Props) {
  return (
    <div className="rounded-lg border bg-card p-4 flex flex-col gap-1">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      {subLabel && <p className="text-xs text-muted-foreground">{subLabel}</p>}
    </div>
  );
}
