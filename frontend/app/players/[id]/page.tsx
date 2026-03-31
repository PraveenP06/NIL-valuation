import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { fetchPlayerValuation } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { PlayerHero } from "@/components/player/PlayerHero";
import { ScoreBreakdownChart } from "@/components/player/ScoreBreakdownChart";
import { PublicValuationsTable } from "@/components/player/PublicValuationsTable";

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  try {
    const { id } = await params;
    const v = await fetchPlayerValuation(Number(id), 2025);
    return {
      title: `${v.name} NIL Valuation | CFB NIL`,
      description: `${v.name} (${v.position ?? ""}, ${v.school ?? ""}) — model NIL valuation and score breakdown.`,
    };
  } catch {
    return { title: "Player Not Found | CFB NIL" };
  }
}

export default async function PlayerDetailPage({ params }: Props) {
  const { id } = await params;
  let valuation;
  try {
    valuation = await fetchPlayerValuation(Number(id), 2025);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <div className="container py-8 max-w-3xl space-y-6">
      <PlayerHero valuation={valuation} />
      <ScoreBreakdownChart valuation={valuation} />
      <PublicValuationsTable entries={valuation.public_valuations} />
    </div>
  );
}
