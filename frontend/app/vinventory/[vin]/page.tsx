import type { Metadata } from "next";
import { permanentRedirect } from "next/navigation";

import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";
import { vehiclePageMetadata, vehicleDetailJsonLd, fetchVehicleServer } from "@/lib/seo";

type Props = { params: { vin: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const vehicle = await fetchVehicleServer(params.vin);
  if (!vehicle) return { title: "Vehicle Not Found" };
  return vehiclePageMetadata(vehicle);
}

export default async function VInventoryDetailPage({ params }: Props) {
  const vehicle = await fetchVehicleServer(params.vin);
  // If the URL contains a raw 17-char VIN, permanently redirect to the slug URL
  // so the public VIN sequence is never exposed to crawlers or bookmarks.
  if (vehicle && params.vin.length === 17 && vehicle.public_slug) {
    permanentRedirect(`/vinventory/${vehicle.public_slug}`);
  }
  return (
    <main className="page-stack">
      {vehicle && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(vehicleDetailJsonLd(vehicle)) }}
        />
      )}
      <VehicleDetailPanel vin={params.vin} />
    </main>
  );
}
