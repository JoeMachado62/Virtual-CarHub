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
        source: "/:slug.html",
        destination: "/:slug"
      }
    ];
  }
};

module.exports = nextConfig;
