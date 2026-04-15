import { Suspense } from "react";
import type { Metadata } from "next";

import { InventoryExplorer } from "@/components/InventoryExplorer";
import { deslugify, makeModelTrimPageMetadata, vehicleOfferJsonLd } from "@/lib/seo";

type Props = { params: { make: string; model: string; trim: string } };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return makeModelTrimPageMetadata(
    deslugify(params.make),
    deslugify(params.model),
    deslugify(params.trim),
  );
}

export default function MakeModelTrimPage({ params }: Props) {
  const make = deslugify(params.make);
  const model = deslugify(params.model);
  const trim = deslugify(params.trim);
  return (
    <main className="page-stack">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(vehicleOfferJsonLd({ make, model, trim })),
        }}
      />
      <Suspense fallback={<div className="card">Loading inventory search...</div>}>
        <InventoryExplorer initialMake={make} initialModel={model} initialTrim={trim} />
      </Suspense>
    </main>
  );
}
