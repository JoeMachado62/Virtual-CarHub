import { ConditionReportDocument } from "@/components/ConditionReportDocument";

export default function ConditionReportPage({ params }: { params: { vin: string } }) {
  return <ConditionReportDocument vin={params.vin} />;
}
