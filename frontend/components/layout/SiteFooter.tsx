export function SiteFooter() {
  return (
    <footer className="border-t py-6 mt-8">
      <div className="container flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-muted-foreground">
        <p>
          Data: <span className="font-medium">CollegeFootballData.com</span> ·
          Season: <span className="font-medium">2025</span>
        </p>
        <p>Valuations are model estimates, not actual deal figures.</p>
      </div>
    </footer>
  );
}
