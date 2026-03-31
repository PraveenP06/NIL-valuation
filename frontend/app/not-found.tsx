import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 p-8 text-center">
      <h2 className="text-2xl font-bold">404 — Not Found</h2>
      <p className="text-muted-foreground">
        This player or school doesn&apos;t exist in our database.
      </p>
      <Button asChild>
        <Link href="/">Back to Leaderboard</Link>
      </Button>
    </div>
  );
}
