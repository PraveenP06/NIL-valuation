import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchSchoolTop } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { PlayerTable } from "@/components/leaderboard/PlayerTable";
import type { LeaderboardPlayer } from "@/lib/types";

type Props = { params: Promise<{ name: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { name } = await params;
  const school = decodeURIComponent(name);
  return {
    title: `${school} — Top Players | CFB NIL Valuation`,
    description: `Top NIL valuations for ${school} football players.`,
  };
}

export default async function SchoolPage({ params }: Props) {
  const { name } = await params;
  const school = decodeURIComponent(name);

  let data;
  try {
    data = await fetchSchoolTop(school, 2025, 25);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const players: LeaderboardPlayer[] = data.data.map((p) => ({
    ...p,
    public_nil_value: null,
    public_source: null,
  }));

  return (
    <div className="container py-8 space-y-6">
      <div className="space-y-1">
        <h1 className="font-display text-4xl font-bold tracking-wide">
          <span className="text-primary gold-glow">{school}</span>
        </h1>
        <p className="text-muted-foreground text-sm">
          Top {players.length} players by NIL value · {data.season} season
        </p>
      </div>
      <PlayerTable players={players} offset={0} />
    </div>
  );
}
