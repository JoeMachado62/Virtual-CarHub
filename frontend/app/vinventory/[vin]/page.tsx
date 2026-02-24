import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";

export default function VInventoryDetailPage({ params }: { params: { vin: string } }) {
  return (
    <main>
      <VehicleDetailPanel vin={params.vin} />
    </main>
  );
}
