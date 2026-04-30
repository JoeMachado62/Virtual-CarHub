import { DashboardShell } from "@/components/DashboardShell";

export default function DashboardPage({
  searchParams
}: {
  searchParams?: { vin?: string | string[] | undefined };
}) {
  const requestedVin = Array.isArray(searchParams?.vin) ? searchParams?.vin[0] : searchParams?.vin;

  return (
    <main className="page-stack">
      <DashboardShell requestedVin={requestedVin} />
    </main>
  );
}
