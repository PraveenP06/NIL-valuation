export function SiteFooter() {
  return (
    <footer className="border-t border-border/60 py-6 mt-8">
      <div className="container flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>
            Data: <span className="text-foreground/70 font-medium">CollegeFootballData.com</span>
          </span>
          <span className="text-border">|</span>
          <span>
            Season: <span className="text-foreground/70 font-medium">2025</span>
          </span>
        </div>
        <p className="text-center sm:text-right">
          Valuations are model estimates — not actual deal figures.
        </p>
      </div>
    </footer>
  );
}
