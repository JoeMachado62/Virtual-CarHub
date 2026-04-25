/* eslint-disable @next/next/no-img-element */
const CONTACT_OPTIONS = [
  {
    title: "Buyer support",
    body: "Questions about inventory, My Garage, inspection reports, or how the buying process works.",
    action: "info@virtualcarhub.com"
  },
  {
    title: "Ask Danny",
    body: "Ask Danny, your AI deal advisor, to help describe the vehicle and deal you want.",
    action: "+1 833-EZ-AUTOS"
  },
  {
    title: "Purchase + delivery",
    body: "Once you are moving forward, logistics and delivery questions stay connected to the same buying process.",
    action: "VirtualCarHub operations"
  }
];

export default function ContactPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact" id="talk-to-danny">
        <div className="section-heading">
          <p className="section-eyebrow">Contact</p>
          <h1>Need help with a car, financing, or delivery?</h1>
          <p className="muted-copy">
            Ask Danny or reach the VirtualCarHub team. We keep your questions, saved vehicles, inspection reports,
            and purchase steps in one place.
          </p>
        </div>
      </section>

      <section className="section-shell split-section">
        <div className="marketing-grid single-column">
          {CONTACT_OPTIONS.map((item) => (
            <article key={item.title} className="feature-panel">
              <h3>{item.title}</h3>
              <p>{item.body}</p>
              <p className="contact-action">{item.action}</p>
            </article>
          ))}
        </div>
        <div className="story-visual">
          <img src="/assets/images/contact/contact-bg.webp" alt="Contact VirtualCarHub" />
        </div>
      </section>
    </main>
  );
}
