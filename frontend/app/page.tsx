import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <section className="hero">
        <h1>The Dealership Run by Code, Not Commission</h1>
        <p>
          Virtual-CarHub is an AI-first flat-fee virtual dealership with Quick Match intake, transparent pricing,
          and a 7-day return flow.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Link className="button" href={"/vinventory" as any}>
            Explore Inventory
          </Link>
          <Link className="button" href="/dashboard">
            Open Client Dashboard
          </Link>
          <Link className="button ghost" href="/admin">
            Open Admin Workspace
          </Link>
        </div>
      </section>

      <section className="grid two" style={{ marginTop: 16 }}>
        <article className="card">
          <h3>Quick Match MVP</h3>
          <p>5-step intake with simplified BFV scoring and confidence labels.</p>
        </article>
        <article className="card">
          <h3>PRD-Aligned API</h3>
          <p>FastAPI backend includes route map from Appendix B and state-machine enforcement.</p>
        </article>
        <article className="card">
          <h3>Danny Chat</h3>
          <p>Buyer-facing conversational assistant with status/recommendation tooling and escalation behavior.</p>
        </article>
        <article className="card">
          <h3>Returns + Audit</h3>
          <p>7-day return workflow with audit events, refund processing, and admin visibility.</p>
        </article>
      </section>
    </main>
  );
}
