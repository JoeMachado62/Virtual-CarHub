/* eslint-disable @next/next/no-img-element */
const CONTACT_OPTIONS = [
  {
    title: "Buyer support",
    body: "Questions about inventory, My Garage, condition reports, or how the buying process works.",
    action: "info@virtualcarhub.com"
  },
  {
    title: "Talk to Danny",
    body: "Use the assistant-driven flow when you want help describing the vehicle and deal you are trying to build.",
    action: "+1 833-EZ-AUTOS"
  },
  {
    title: "Delivery + acquisition",
    body: "Once you are deep in the purchase loop, logistics and handoff questions should stay in the same workflow.",
    action: "VirtualCarHub operations"
  }
];

export default function ContactPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact" id="talk-to-danny">
        <div className="section-heading">
          <p className="section-eyebrow">Contact</p>
          <h1>Talk to a real system with a real workflow behind it.</h1>
          <p className="muted-copy">
            The goal is to keep buyers inside one coherent experience instead of bouncing between forms, inboxes, and
            disconnected dealership departments.
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
