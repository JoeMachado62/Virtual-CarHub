/* eslint-disable @next/next/no-img-element */
"use client";

import { useEffect, useState } from "react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/ThemeToggle";
import {
  FaInstagram,
  FaThreads,
  FaTiktok,
  FaXTwitter,
  FaPinterest,
  FaTumblr,
  FaYoutube,
  FaLinkedinIn,
  FaFacebookF,
} from "react-icons/fa6";

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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const isEmbedRoute = pathname.startsWith("/embed/");

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

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
              <a href="https://www.instagram.com/virtual_carhub" target="_blank" rel="noreferrer" aria-label="Instagram"><FaInstagram /></a>
              <a href="https://www.threads.com/@virtual_carhub" target="_blank" rel="noreferrer" aria-label="Threads"><FaThreads /></a>
              <a href="https://www.tiktok.com/@virtual_carhub" target="_blank" rel="noreferrer" aria-label="TikTok"><FaTiktok /></a>
              <a href="https://x.com/virtualcarhub" target="_blank" rel="noreferrer" aria-label="X"><FaXTwitter /></a>
              <a href="https://www.pinterest.com/virtualcarhub" target="_blank" rel="noreferrer" aria-label="Pinterest"><FaPinterest /></a>
              <a href="https://www.tumblr.com/virtualcarhub" target="_blank" rel="noreferrer" aria-label="Tumblr"><FaTumblr /></a>
              <a href="https://www.youtube.com/@virtualcarhub" target="_blank" rel="noreferrer" aria-label="YouTube"><FaYoutube /></a>
              <a href="https://www.linkedin.com/company/virtualcarhub" target="_blank" rel="noreferrer" aria-label="LinkedIn"><FaLinkedinIn /></a>
              <a href="https://www.facebook.com/virtualcarhub" target="_blank" rel="noreferrer" aria-label="Facebook"><FaFacebookF /></a>
              <ThemeToggle />
            </div>
          </div>
        </div>

        <div className="navbar-shell">
          <div className="shell navbar">
            <Link href="/" className="brand-lockup">
              <img src={logoPath} alt="VirtualCarHub" className="brand-mark" />
            </Link>

            <div className="nav-actions nav-actions-inline">
              <Link href="/dashboard" className="button secondary">
                My Garage
              </Link>
              <Link href="/contact#talk-to-danny" className="button">
                Ask Danny
              </Link>
            </div>

            <button
              className="hamburger-btn"
              aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileMenuOpen}
              onClick={() => setMobileMenuOpen((v) => !v)}
            >
              <span className={`hamburger-icon ${mobileMenuOpen ? "open" : ""}`}>
                <span />
                <span />
                <span />
              </span>
            </button>

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

            <div className="nav-actions nav-actions-desktop">
              <Link href="/dashboard" className="button secondary">
                My Garage
              </Link>
              <Link href="/contact#talk-to-danny" className="button">
                Ask Danny
              </Link>
            </div>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="mobile-nav-overlay" onClick={() => setMobileMenuOpen(false)} />
        )}
        <nav
          className={`mobile-nav-drawer ${mobileMenuOpen ? "open" : ""}`}
          aria-label="Mobile navigation"
        >
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`mobile-nav-link ${isActive(pathname, item.href) ? "active" : ""}`}
              onClick={() => setMobileMenuOpen(false)}
            >
              {item.label}
            </Link>
          ))}
          <div className="mobile-nav-actions">
            <Link href="/dashboard" className="button secondary" onClick={() => setMobileMenuOpen(false)}>
              My Garage
            </Link>
            <Link href="/contact#talk-to-danny" className="button" onClick={() => setMobileMenuOpen(false)}>
              Ask Danny
            </Link>
          </div>
        </nav>
      </header>

      <div className="page-body">
        <div className="shell">{children}</div>
      </div>

      <footer className="site-footer">
        <div className="shell footer-grid">
          <section>
            <img src={logoPath} alt="VirtualCarHub" className="footer-logo" />
            <p className="footer-copy">
              VirtualCarHub helps buyers access wholesale channels, compare the real deal math, and avoid commissioned
              sales pressure.
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
              <Link href="/vinventory">Request Inspection Report</Link>
              <Link href="/contact#talk-to-danny">Ask Danny</Link>
              <Link href="/blog">Latest Insights</Link>
            </div>
          </section>
        </div>
      </footer>
    </>
  );
}
