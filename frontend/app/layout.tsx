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
  description:
    "VirtualCarHub helps consumers acquire vehicles through dealer-only wholesale channels without traditional retail overhead.",
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
