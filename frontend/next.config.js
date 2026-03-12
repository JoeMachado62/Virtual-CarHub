/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    typedRoutes: true
  },
  async rewrites() {
    return [
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
