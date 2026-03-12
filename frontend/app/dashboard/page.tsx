import { DashboardShell } from "@/components/DashboardShell";

export default function DashboardPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <p className="section-eyebrow">My Garage</p>
        <h1>Buyer dashboard, deal tracking, and saved-vehicle workflow.</h1>
      </section>
      <DashboardShell />
    </main>
  );
}
