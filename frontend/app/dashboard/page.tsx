import { DashboardShell } from "@/components/DashboardShell";

export default function DashboardPage({
  searchParams
}: {
  searchParams?: { vin?: string | string[] | undefined };
}) {
  const requestedVin = Array.isArray(searchParams?.vin) ? searchParams?.vin[0] : searchParams?.vin;

  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">My Garage</p>
        <h1>Saved vehicles, inspection reports, and purchase status in one place.</h1>
      </section>
      <DashboardShell requestedVin={requestedVin} />
    </main>
  );
}
