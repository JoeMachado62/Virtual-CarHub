/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

const STEPS = [
  "Set your budget, vehicle goals, and ownership priorities.",
  "Share the information needed to understand your buying power.",
  "Unlock pre-approved buyer status so inspection reports and next-step details can open up.",
  "Move from selected vehicle to purchase, paperwork, and delivery with fewer handoffs."
];

export default function FinancingPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <div className="section-heading">
          <p className="section-eyebrow">Financing</p>
          <h1>Get pre-approved before you spend time on the wrong cars.</h1>
          <p className="muted-copy">
            Financing is not just a checkout step. It helps Danny show vehicles that fit your real budget and unlocks
            deeper inspection details when you are ready.
          </p>
        </div>
      </section>

      <section className="section-shell split-section">
        <div className="story-copy">
          <p className="section-eyebrow">Why It Matters</p>
          <h2>Know your buying power before you fall in love with a car.</h2>
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
          <img src="/assets/images/about/stat-bg.webp" alt="Financing and wholesale search visual" />
        </div>
      </section>

      <section className="section-shell">
        <div className="marketing-grid">
          <article className="feature-panel">
            <h3>Budget-first search</h3>
            <p>Search inventory with realistic numbers before you get attached to a vehicle.</p>
          </article>
          <article className="feature-panel">
            <h3>Inspection reports at the right time</h3>
            <p>Detailed inspection requests stay focused on vehicles you are actually ready to consider.</p>
          </article>
          <article className="feature-panel">
            <h3>One guided process</h3>
            <p>The same account that helps you find vehicles also tracks funding, paperwork, and delivery.</p>
          </article>
        </div>
      </section>
    </main>
  );
}
