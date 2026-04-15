import { Suspense } from "react";
import type { Metadata } from "next";

import { InventoryExplorer } from "@/components/InventoryExplorer";
import { deslugify, makePageMetadata, vehicleOfferJsonLd } from "@/lib/seo";

type Props = { params: { make: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return makePageMetadata(deslugify(params.make));
}

export default function MakePage({ params }: Props) {
  const make = deslugify(params.make);
  return (
    <main className="page-stack">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(vehicleOfferJsonLd({ make })) }}
      />
      <Suspense fallback={<div className="card">Loading inventory search...</div>}>
        <InventoryExplorer initialMake={make} />
      </Suspense>
    </main>
  );
}
