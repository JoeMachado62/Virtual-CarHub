/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

import { DealBuilderPanel } from "@/components/DealBuilderPanel";
import { InventoryPreview } from "@/components/InventoryPreview";

const VALUE_POINTS = [
  {
    title: "Tell Us What You Want",
    body: "Start with the exact vehicle, payment target, mileage, or feature set you need. We work backward from your deal."
  },
  {
    title: "We Search Wholesale Inventory",
    body: "Live feeds from retail and auction sources give you far more coverage than a single dealer lot."
  },
  {
    title: "Review Before You Commit",
    body: "Pre-approved buyers can request a VCH condition report before the acquisition loop moves forward."
  },
  {
    title: "We Handle the Deal End-to-End",
    body: "Financing, negotiation, paperwork, transport, and final delivery stay in one controlled workflow."
  }
];

const PROCESS_STEPS = [
  "Build your deal and save vehicles to My Garage.",
  "Get pre-approved so deeper inspection workflows can unlock.",
  "Request the VCH condition report on the vehicles you are serious about.",
  "Approve the vehicle and move into acquisition, paperwork, and delivery."
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
              Search wholesale inventory, save vehicles to My Garage, request condition reports, and move through the
              full buying workflow without the usual dealership friction.
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
                <strong>Buyer</strong>
                <span>Garage + approval workflow</span>
              </div>
            </div>
          </div>

          <DealBuilderPanel />
        </div>
      </section>

      <section className="section-shell">
        <div className="section-heading">
          <p className="section-eyebrow">How It Works</p>
          <h2>A better front door for the entire buying process.</h2>
          <p className="muted-copy">
            The old prototype cards were internal MVP notes. This is the customer-facing version of that same system.
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
          <h2>Preview the vehicles flowing through the new stack.</h2>
          <p className="muted-copy">
            The preview below pulls current auction inventory from the backend so this page stays tied to the actual
            buying system.
          </p>
          <div className="hero-actions">
            <Link className="button" href={"/vinventory?source_type=ove" as any}>
              See OVE Inventory
            </Link>
          </div>
        </div>

        <InventoryPreview />
      </section>

      <section className="section-shell story-panel">
        <div className="story-copy">
          <p className="section-eyebrow">Build With Confidence</p>
          <h2>From search to signed intent, one controlled workflow.</h2>
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
              Talk to Danny
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
