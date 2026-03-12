/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

const STEPS = [
  "Set your budget, vehicle goals, and ownership priorities.",
  "Submit the buyer profile and financing information.",
  "Unlock pre-approved buyer status for deeper vehicle due diligence.",
  "Move from selected vehicle to acquisition and paperwork with fewer handoffs."
];

export default function FinancingPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <div className="section-heading">
          <p className="section-eyebrow">Financing</p>
          <h1>Pre-approval is the gateway to the deeper buying workflow.</h1>
          <p className="muted-copy">
            Financing is not just a checkout step. It determines which vehicles you can move forward on and when the
            condition-report process should unlock.
          </p>
        </div>
      </section>

      <section className="section-shell split-section">
        <div className="story-copy">
          <p className="section-eyebrow">Why It Matters</p>
          <h2>Get qualified before you commit time to the wrong vehicles.</h2>
          <ol className="step-list">
            {STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="hero-actions">
            <Link className="button" href="/dashboard">
              Open Buyer Dashboard
            </Link>
            <Link className="button secondary" href="/contact#talk-to-danny">
              Ask a Financing Question
            </Link>
          </div>
        </div>
        <div className="story-visual">
          <img src="/assets/images/about/stat-bg.webp" alt="Financing workflow visual" />
        </div>
      </section>

      <section className="section-shell">
        <div className="marketing-grid">
          <article className="feature-panel">
            <h3>Budget-first search</h3>
            <p>Search inventory with realistic deal parameters instead of getting attached before the numbers work.</p>
          </article>
          <article className="feature-panel">
            <h3>Condition report gating</h3>
            <p>Inspection and deeper auction-detail requests stay aligned with real buyer intent and qualification.</p>
          </article>
          <article className="feature-panel">
            <h3>One workflow</h3>
            <p>The same system that matches you to vehicles also tracks acquisition, funding, paperwork, and delivery.</p>
          </article>
        </div>
      </section>
    </main>
  );
}
