import type { Metadata } from "next";
import { permanentRedirect } from "next/navigation";

import { VehicleDetailPanel } from "@/components/VehicleDetailPanel";
import { vehiclePageMetadata, vehicleDetailJsonLd, fetchVehicleServer } from "@/lib/seo";

type Props = { params: { vin: string; slug: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const vehicle = await fetchVehicleServer(params.vin);
  if (!vehicle) return { title: "Vehicle Not Found" };
  return vehiclePageMetadata(vehicle);
}

export default async function VehicleCanonicalPage({ params }: Props) {
  const vehicle = await fetchVehicleServer(params.vin);
  if (vehicle && params.vin.length === 17 && vehicle.public_slug) {
    permanentRedirect(`/cars/${vehicle.public_slug}/${params.slug}`);
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
