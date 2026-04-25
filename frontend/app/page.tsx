/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

import { DealBuilderPanel } from "@/components/DealBuilderPanel";
import { InventoryPreview } from "@/components/InventoryPreview";

// Force dynamic rendering so every request gets the latest JS bundles
export const dynamic = "force-dynamic";

const VALUE_POINTS = [
  {
    title: "Tell Us What You Want",
    body: "Share the vehicle, payment target, mileage, and must-have features. Danny turns that into a smarter wholesale search."
  },
  {
    title: "We Search Dealer-Only Channels",
    body: "We look across the same wholesale channels dealers use to stock their lots, then show you options built around your budget."
  },
  {
    title: "Verify Before You Move Forward",
    body: "Pre-approved buyers can review inspection details and condition reports before taking the next step."
  },
  {
    title: "We Handle the Hard Parts",
    body: "Financing, negotiation, paperwork, transport, and delivery stay organized in one guided buying process."
  }
];

const PROCESS_STEPS = [
  "Build your deal and save vehicles to My Garage.",
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
            <p className="section-eyebrow">AI-First Wholesale Buying</p>
            <h1>
              The Dealership Run by <span>Code</span>, Not Commission.
            </h1>
            <p className="hero-lead">
              Save thousands on your next car. Buy direct from the same wholesale channels dealers use to stock their
              inventories, with Danny helping you compare the math before you move forward.
            </p>
            <div className="hero-actions">
              <Link className="button" href={"/vinventory" as any}>
                Browse VInventory
              </Link>
              <Link className="button secondary" href="/about">
                Learn More
              </Link>
            </div>
            <div className="hero-metrics">
              <div className="metric">
                <strong>0%</strong>
                <span>Commission</span>
              </div>
              <div className="metric">
                <strong>Live</strong>
                <span>Auction + retail feeds</span>
              </div>
              <div className="metric">
                <strong>Danny</strong>
                <span>Deal math + buyer guidance</span>
              </div>
            </div>
          </div>

          <DealBuilderPanel />
        </div>
      </section>

      <section className="section-shell">
        <div className="section-heading">
          <p className="section-eyebrow">How It Works</p>
          <h2>Wholesale access, clear math, and no commissioned pressure.</h2>
          <p className="muted-copy">
            Tell us what you want, compare real options, and move forward only when the vehicle and numbers make sense.
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

      <section className="section-shell split-section">
        <div className="section-heading">
          <p className="section-eyebrow">Live Inventory</p>
          <h2>Browse vehicles we can help you buy smarter.</h2>
          <p className="muted-copy">
            Start with live inventory, then use My Garage to save favorites, request inspection details, and compare the
            true deal.
          </p>
          <div className="hero-actions">
            <Link className="button" href={"/vinventory?source_type=auction" as any}>
              See Auction Inventory
            </Link>
          </div>
        </div>

        <InventoryPreview />
      </section>

      <section className="section-shell story-panel">
        <div className="story-copy">
          <p className="section-eyebrow">Build With Confidence</p>
          <h2>From first search to final delivery, Danny keeps the deal moving.</h2>
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
