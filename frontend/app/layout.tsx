import "./globals.css";
import type { Metadata, Viewport } from "next";

import { SiteChrome } from "@/components/SiteChrome";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://app.virtualcarhub.com"),
  title: {
    default: "VirtualCarHub",
    template: "%s | VirtualCarHub",
  },
  description: "Buy from wholesale channels, compare the real deal math, and avoid commissioned sales pressure.",
  icons: {
    icon: "/assets/images/logo/logo.svg",
  },
  robots: { index: true, follow: true },
  verification: {
    google: "0lBtMLFV7TgqUXdUO5H3Mx0z-C4Zl04y5iuXUvxgj0A",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body>
        <SiteChrome>{children}</SiteChrome>
      </body>
    </html>
  );
}
