import { Suspense } from "react";

import { InventoryExplorer } from "@/components/InventoryExplorer";

export const dynamic = "force-dynamic";

export default function VInventoryPage() {
  return (
    <main className="page-stack">
      <Suspense fallback={<div className="card">Loading inventory search...</div>}>
        <InventoryExplorer />
      </Suspense>
    </main>
  );
}
