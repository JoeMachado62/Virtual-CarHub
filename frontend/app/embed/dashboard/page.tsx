import { DashboardShell } from "@/components/DashboardShell";

export default function EmbeddedDashboardPage({
  searchParams
}: {
  searchParams?: { vin?: string | string[] | undefined };
}) {
  const requestedVin = Array.isArray(searchParams?.vin) ? searchParams?.vin[0] : searchParams?.vin;

  return <DashboardShell requestedVin={requestedVin} />;
}
