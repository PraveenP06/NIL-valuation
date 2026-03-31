import type { Metadata } from "next";
import { LeaderboardContainer } from "@/components/leaderboard/LeaderboardContainer";

export const metadata: Metadata = {
  title: "NIL Leaderboard | CFB NIL Valuation",
  description:
    "Model-driven NIL valuations for 15,000+ college football players. Filter by position, conference, and class year.",
};

export default function LeaderboardPage() {
  return <LeaderboardContainer />;
}
