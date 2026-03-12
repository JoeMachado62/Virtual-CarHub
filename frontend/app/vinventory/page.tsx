import { Suspense } from "react";

import { InventoryExplorer } from "@/components/InventoryExplorer";

export default function VInventoryPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">VInventory</p>
        <h1>Search live inventory, save vehicles, and move buyers into action.</h1>
        <p className="muted-copy">
          This is the controlled search surface for auction and retail inventory, not a disconnected marketing page.
        </p>
      </section>
      <Suspense fallback={<div className="card">Loading inventory search...</div>}>
        <InventoryExplorer />
      </Suspense>
    </main>
  );
}
