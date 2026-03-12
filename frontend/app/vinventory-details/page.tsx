import { redirect } from "next/navigation";

export default function LegacyVinventoryDetailsPage({
  searchParams
}: {
  searchParams: { vin?: string };
}) {
  const vin = searchParams.vin?.trim();

  if (vin) {
    redirect(`/vinventory/${encodeURIComponent(vin)}`);
  }

  redirect("/vinventory");
}
