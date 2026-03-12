const ARTICLES = [
  {
    title: "How wholesale inventory should work in a buyer-first experience",
    summary: "Why search, qualification, and condition reporting need to live in the same system instead of scattered tools."
  },
  {
    title: "What a VCH condition report is meant to solve",
    summary: "How deeper auction detail fits into a purchase flow once a buyer is actually ready to move."
  },
  {
    title: "Why My Garage matters more than a favorites list",
    summary: "Saved vehicles should connect to negotiation, financing, and acquisition workflows instead of just bookmarks."
  }
];

export default function BlogPage() {
  return (
    <main className="page-stack">
      <section className="section-shell page-hero compact">
        <div className="section-heading">
          <p className="section-eyebrow">Blog</p>
          <h1>Notes on inventory, buying workflows, financing, and digital dealership design.</h1>
          <p className="muted-copy">
            This section can grow into a proper content hub later. For now it gives the Next app a branded editorial
            surface instead of sending visitors back into WordPress.
          </p>
        </div>
      </section>

      <section className="section-shell">
        <div className="marketing-grid">
          {ARTICLES.map((article) => (
            <article key={article.title} className="feature-panel">
              <p className="section-eyebrow">Coming Soon</p>
              <h3>{article.title}</h3>
              <p>{article.summary}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
