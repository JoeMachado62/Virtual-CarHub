import { permanentRedirect } from "next/navigation";

import { ConditionReportDocument } from "@/components/ConditionReportDocument";
import { fetchVehicleServer } from "@/lib/seo";

export default async function ConditionReportPage({ params }: { params: { vin: string } }) {
  if (params.vin.length === 17) {
    const vehicle = await fetchVehicleServer(params.vin);
    if (vehicle?.public_slug) {
      permanentRedirect(`/vinventory/${vehicle.public_slug}/condition-report`);
    }
  }
  return <ConditionReportDocument vin={params.vin} />;
}
