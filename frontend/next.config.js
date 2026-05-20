/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    typedRoutes: true
  },
  async headers() {
    return [
      {
        // Prevent browser from caching HTML pages so new JS bundles are always loaded
        source: "/:path((?!_next/static|assets).*)",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ];
  },
  async rewrites() {
    const defaultApiBase =
      process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000/v1" : "http://backend:8000/v1";
    const apiBase = (process.env.API_INTERNAL_BASE || defaultApiBase).replace(/\/$/, "");

    return [
      {
        source: "/v1/:path*",
        destination: `${apiBase}/:path*`
      },
      {
        source: "/favicon.ico",
        destination: "/assets/images/logo/logo.svg"
      },
      {
        source: "/index.html",
        destination: "/"
      },
      {
        source: "/about.html",
        destination: "/about"
      },
      {
        source: "/blog/index.html",
        destination: "/blog"
      },
      {
        source: "/calculator.html",
        destination: "/financing"
      },
      {
        source: "/contact.html",
        destination: "/contact"
      },
      {
        source: "/inventory.html",
        destination: "/inventory"
      },
      {
        source: "/vinventory.html",
        destination: "/vinventory"
      },
      {
        source: "/vinventory-details.html",
        destination: "/vinventory-details"
      },
      {
        source: "/dashboard.html",
        destination: "/dashboard"
      },
      {
        source: "/admin-dashboard.html",
        destination: "/admin"
      },
      {
        source: "/client-dashboard.html",
        destination: "/dashboard"
      },
      {
        source: "/premium-dashboard.html",
        destination: "/dashboard"
      }
    ];
  }
};

module.exports = nextConfig;
