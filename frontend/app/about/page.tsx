/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

const CREW = [
  {
    title: "Find the Right Inventory",
    body: "Danny searches beyond one dealer's lot to find vehicles that fit your budget, mileage, features, and timing."
  },
  {
    title: "Explain the Deal Math",
    body: "Danny helps you understand pricing, fees, financing, and savings before you spend time on the wrong car."
  },
  {
    title: "Coordinate the Purchase",
    body: "From inspection reports to paperwork and delivery, VirtualCarHub keeps the buying process organized."
  }
];

export default function AboutPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <div className="section-heading">
          <p className="section-eyebrow">About VirtualCarHub</p>
          <h1>We rebuilt car buying around the buyer, not the commission table.</h1>
          <p className="muted-copy">
            VirtualCarHub helps you buy from wholesale channels, compare the real numbers, and avoid the pressure built
            into traditional car sales.
          </p>
        </div>
      </section>

      <section className="section-shell split-section">
        <div className="story-visual">
          <img src="/assets/images/about/04.webp" alt="VirtualCarHub team visual" />
        </div>
        <div className="story-copy">
          <p className="section-eyebrow">Your Deal Advisor</p>
          <h2>Danny works for the buyer.</h2>
          <div className="marketing-grid single-column">
            {CREW.map((item) => (
              <article key={item.title} className="feature-panel">
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section-shell">
        <div className="section-heading">
          <p className="section-eyebrow">What Makes It Different</p>
          <h2>Wholesale access is only useful when the process is clear.</h2>
        </div>
        <div className="marketing-grid">
          <article className="feature-panel">
            <h3>More than listings</h3>
            <p>Search, My Garage, inspection reports, and purchase steps stay connected so you always know what comes next.</p>
          </article>
          <article className="feature-panel">
            <h3>Pre-approval matters</h3>
            <p>Getting qualified helps you focus on vehicles that fit your real buying power.</p>
          </article>
          <article className="feature-panel">
            <h3>Transparency beats pressure</h3>
            <p>Instead of commissioned sales pressure, Danny shows the math and helps you decide when to move forward.</p>
          </article>
        </div>
        <div className="hero-actions">
          <Link className="button" href={"/vinventory" as any}>
            Browse Inventory
          </Link>
        </div>
      </section>
    </main>
  );
}
