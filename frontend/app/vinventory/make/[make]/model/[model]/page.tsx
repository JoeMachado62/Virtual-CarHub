import { Suspense } from "react";
import type { Metadata } from "next";

import { InventoryExplorer } from "@/components/InventoryExplorer";
import { deslugify, makeModelPageMetadata, vehicleOfferJsonLd } from "@/lib/seo";

type Props = { params: { make: string; model: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return makeModelPageMetadata(deslugify(params.make), deslugify(params.model));
}

export default function MakeModelPage({ params }: Props) {
  const make = deslugify(params.make);
  const model = deslugify(params.model);
  return (
    <main className="page-stack">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(vehicleOfferJsonLd({ make, model })) }}
      />
      <Suspense fallback={<div className="card">Loading inventory search...</div>}>
        <InventoryExplorer initialMake={make} initialModel={model} />
      </Suspense>
    </main>
  );
}
