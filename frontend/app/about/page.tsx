/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

const CREW = [
  {
    title: "The Eyes",
    body: "Scans live inventory feeds and auction lanes to find vehicles that fit your constraints instead of a dealer's floorplan."
  },
  {
    title: "The Voice",
    body: "Danny keeps the buyer experience conversational while the workflow behind the scenes stays structured and trackable."
  },
  {
    title: "The Hands",
    body: "From condition-report requests to paperwork and delivery coordination, the system keeps every step moving in one pipeline."
  }
];

export default function AboutPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <div className="section-heading">
          <p className="section-eyebrow">About VirtualCarHub</p>
          <h1>We rebuilt the dealership workflow around the buyer, not the commission table.</h1>
          <p className="muted-copy">
            VirtualCarHub combines live wholesale search, guided financing, buyer qualification, and acquisition
            workflows into one controlled digital buying experience.
          </p>
        </div>
      </section>

      <section className="section-shell split-section">
        <div className="story-visual">
          <img src="/assets/images/about/04.webp" alt="VirtualCarHub team visual" />
        </div>
        <div className="story-copy">
          <p className="section-eyebrow">Your Digital Crew</p>
          <h2>Agents working for the buyer.</h2>
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
          <h2>The frontend, inventory search, and deal flow are designed as one system.</h2>
        </div>
        <div className="marketing-grid">
          <article className="feature-panel">
            <h3>Inventory is not a marketing afterthought</h3>
            <p>Search, My Garage, condition reports, and acquisition actions are connected to the same backend state.</p>
          </article>
          <article className="feature-panel">
            <h3>Pre-approval matters</h3>
            <p>Buyer qualification drives which deeper vehicle workflows unlock, instead of treating every click the same.</p>
          </article>
          <article className="feature-panel">
            <h3>Transparency beats pressure</h3>
            <p>Instead of salesman theatrics, the interface explains what is available now and what requires the next step.</p>
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
