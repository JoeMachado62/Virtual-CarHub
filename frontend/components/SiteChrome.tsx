/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/ThemeToggle";

const NAV_ITEMS: Array<{ href: Route; label: string }> = [
  { href: "/", label: "Home" },
  { href: "/vinventory", label: "VInventory" },
  { href: "/financing", label: "Financing" },
  { href: "/blog", label: "Blog" },
  { href: "/about", label: "About Us" },
  { href: "/contact", label: "Contact" }
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function resolveLogoPath(theme: string | undefined) {
  return theme === "light" ? "/assets/images/logo/VCH Logo.png" : "/assets/images/logo/VirtualCarHub white.png";
}

export function SiteChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [logoPath, setLogoPath] = useState("/assets/images/logo/VirtualCarHub white.png");
  const isEmbedRoute = pathname.startsWith("/embed/");

  useEffect(() => {
    const root = document.documentElement;
    const syncLogo = () => setLogoPath(resolveLogoPath(root.dataset.theme));

    syncLogo();

    const observer = new MutationObserver(syncLogo);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });

    return () => observer.disconnect();
  }, []);

  if (isEmbedRoute) {
    return <div className="page-body page-body-embed">{children}</div>;
  }

  return (
    <>
      <header className="site-header">
        <div className="topbar">
          <div className="shell topbar-inner">
            <div className="topbar-contact">
              <a href="tel:+18333928867">+1 833-EZ-AUTOS</a>
              <a href="mailto:info@virtualcarhub.com">info@virtualcarhub.com</a>
            </div>
            <div className="topbar-tools">
              <a href="https://www.linkedin.com" target="_blank" rel="noreferrer">
                LinkedIn
              </a>
              <a href="https://www.facebook.com" target="_blank" rel="noreferrer">
                Facebook
              </a>
              <ThemeToggle />
            </div>
          </div>
        </div>

        <div className="navbar-shell">
          <div className="shell navbar">
            <Link href="/" className="brand-lockup">
              <img src={logoPath} alt="VirtualCarHub" className="brand-mark" />
            </Link>

            <nav className="site-nav" aria-label="Primary">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`nav-link ${isActive(pathname, item.href) ? "active" : ""}`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            <div className="nav-actions">
              <Link href="/dashboard" className="button secondary">
                My Garage
              </Link>
              <Link href="/contact#talk-to-danny" className="button">
                Talk to Danny
              </Link>
            </div>
          </div>
        </div>
      </header>

      <div className="page-body">
        <div className="shell">{children}</div>
      </div>

      <footer className="site-footer">
        <div className="shell footer-grid">
          <section>
            <img src={logoPath} alt="VirtualCarHub" className="footer-logo" />
            <p className="footer-copy">
              VirtualCarHub is the AI-first wholesale buying experience built around transparency, speed, and buyer
              control.
            </p>
          </section>
          <section>
            <h3>Explore</h3>
            <div className="footer-links">
              <Link href="/vinventory">Browse VInventory</Link>
              <Link href="/financing">Financing</Link>
              <Link href="/about">How It Works</Link>
              <Link href="/contact">Contact</Link>
            </div>
          </section>
          <section>
            <h3>Buyer Tools</h3>
            <div className="footer-links">
              <Link href="/dashboard">My Garage</Link>
              <Link href="/vinventory">Order Condition Report</Link>
              <Link href="/contact#talk-to-danny">Talk to Danny</Link>
              <Link href="/blog">Latest Insights</Link>
            </div>
          </section>
        </div>
      </footer>
    </>
  );
}
