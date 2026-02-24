import { InventoryExplorer } from "@/components/InventoryExplorer";

export default function InventoryPage() {
  return (
    <main>
      <section className="hero" style={{ marginBottom: 12 }}>
        <h1>Inventory</h1>
        <p>
          CarGurus-style discovery with sidebar filters, paginated results, and VIN-level detail pages that swap to
          verified inspection media as deals advance.
        </p>
      </section>
      <InventoryExplorer />
    </main>
  );
}
