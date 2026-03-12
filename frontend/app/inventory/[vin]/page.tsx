import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";

export default function VehicleDetailPage({ params }: { params: { vin: string } }) {
  return (
    <main className="page-stack">
      <VehicleDetailPanel vin={params.vin} />
    </main>
  );
}
