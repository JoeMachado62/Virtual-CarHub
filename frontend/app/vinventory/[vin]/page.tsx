import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";

export default function VInventoryDetailPage({ params }: { params: { vin: string } }) {
  return (
    <main className="page-stack">
      <VehicleDetailPanel vin={params.vin} />
    </main>
  );
}
