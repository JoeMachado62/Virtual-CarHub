import "./globals.css";
import type { Metadata } from "next";

import { SiteChrome } from "@/components/SiteChrome";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://app.virtualcarhub.com"),
  title: {
    default: "VirtualCarHub",
    template: "%s | VirtualCarHub",
  },
  description: "AI-first flat-fee virtual dealership built for smarter wholesale buying.",
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
