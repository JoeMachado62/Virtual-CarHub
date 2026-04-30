/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

import { DealBuilderPanel } from "@/components/DealBuilderPanel";
import { HotDealsPreview } from "@/components/HotDealsPreview";

// Force dynamic rendering so every request gets the latest JS bundles
export const dynamic = "force-dynamic";

const VALUE_POINTS = [
  {
    title: "Tell Us What You Want to Acquire",
    body: "Share the vehicle, budget, mileage, and must-haves. Danny turns your request into a focused wholesale acquisition search."
  },
  {
    title: "We Source Through Wholesale Channels",
    body: "VirtualCarHub helps consumers access vehicle channels previously reserved for licensed dealers."
  },
  {
    title: "We Verify Before You Move Forward",
    body: "Pre-approved buyers can review inspection details and condition reports before committing to the next step."
  },
  {
    title: "We Acquire on Your Behalf",
    body: "Pricing, inspection, purchase coordination, paperwork, transport, and delivery stay organized in one buyer-side process."
  }
];

const PROCESS_STEPS = [
  "Tell Danny what you want to acquire and save opportunities to My Garage.",
  "Get pre-approved so real inspection details can unlock.",
  "Request the VirtualCarHub inspection report on vehicles you are serious about.",
  "Choose the right vehicle and move into purchase, paperwork, and delivery."
];

export default function HomePage() {
  return (
    <main className="page-stack">
      <section className="hero-surface">
        <div className="hero-backdrop" />
        <div className="hero-grid">
          <div className="hero-copy">
            <p className="section-eyebrow">Dealer-Only Wholesale Access</p>
            <h1>
              Buy Where Dealers Buy. <span>Cut Out</span> the Overhead.
            </h1>
            <p className="hero-lead">
              VirtualCarHub helps consumers acquire vehicles through wholesale channels previously reserved for licensed
              dealers — without the commissioned sales pressure, lot overhead, or retail markup built into traditional
              car buying.
            </p>
            <div className="hero-actions">
              <Link className="button" href={"/vinventory" as any}>
                Start Wholesale Search
              </Link>
              <Link className="button secondary" href="#how-it-works">
                See How It Works
              </Link>
            </div>
            <div className="hero-metrics">
              <div className="metric">
                <strong>Wholesale</strong>
                <span>Access</span>
              </div>
              <div className="metric">
                <strong>No Retail</strong>
                <span>Markup</span>
              </div>
              <div className="metric">
                <strong>Buyer-Side</strong>
                <span>Guidance</span>
              </div>
            </div>
          </div>

          <DealBuilderPanel />
        </div>
      </section>

      <section className="section-shell" id="how-it-works">
        <div className="section-heading">
          <p className="section-eyebrow">How It Works</p>
          <h2>We are not a listing site. We are your wholesale acquisition partner.</h2>
          <p className="muted-copy">
            Tell us what you want. We help source, price, inspect, acquire, and deliver the vehicle through dealer-only
            wholesale channels on your behalf.
          </p>
        </div>
        <div className="marketing-grid">
          {VALUE_POINTS.map((item) => (
            <article className="feature-panel" key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-shell split-section hot-deals-section">
        <div className="section-heading">
          <p className="section-eyebrow">Deal of the Hour</p>
          <h2>Danny&apos;s Picks!</h2>
          <p className="muted-copy">
            Vetted and inspected vehicles, priced below what dealers pay at auction. Save one to My Garage, see the
            inspection details, and grab it before someone else does.
          </p>
          <div className="hero-actions">
            <Link className="button" href={"/vinventory?hot_deals=true" as any}>
              View Hot Deals
            </Link>
          </div>
        </div>

        <HotDealsPreview />
      </section>

      <section className="section-shell story-panel">
        <div className="story-copy">
          <p className="section-eyebrow">Build With Confidence</p>
          <h2>From first request to final delivery, Danny keeps the acquisition moving.</h2>
          <ol className="step-list">
            {PROCESS_STEPS.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="hero-actions">
            <Link className="button" href="/financing">
              Start Financing
            </Link>
            <Link className="button secondary" href="/contact#talk-to-danny">
              Ask Danny
            </Link>
          </div>
        </div>

        <div className="story-visual">
          <img src="/assets/images/about/05.webp" alt="Luxury vehicle spotlight" />
        </div>
      </section>
    </main>
  );
}
