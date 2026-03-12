import { Suspense } from "react";

import { InventoryExplorer } from "@/components/InventoryExplorer";

export default function InventoryPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">Inventory</p>
        <h1>Unified search across the same backend inventory engine.</h1>
        <p className="muted-copy">
          This route mirrors VInventory and can be kept as an internal alias while the public product language settles.
        </p>
      </section>
      <Suspense fallback={<div className="card">Loading inventory search...</div>}>
        <InventoryExplorer />
      </Suspense>
    </main>
  );
}
