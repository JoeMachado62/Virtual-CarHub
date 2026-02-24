import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";

export default function VehicleDetailPage({ params }: { params: { vin: string } }) {
  return (
    <main>
      <VehicleDetailPanel vin={params.vin} />
    </main>
  );
}
