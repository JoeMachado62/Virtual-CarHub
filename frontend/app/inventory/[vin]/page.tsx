import { permanentRedirect } from "next/navigation";

import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";
import { fetchVehicleServer } from "@/lib/seo";

export default async function VehicleDetailPage({ params }: { params: { vin: string } }) {
  if (params.vin.length === 17) {
    const vehicle = await fetchVehicleServer(params.vin);
    if (vehicle?.public_slug) {
      permanentRedirect(`/inventory/${vehicle.public_slug}`);
    }
  }
  return (
    <main className="page-stack">
      <VehicleDetailPanel vin={params.vin} />
    </main>
  );
}
