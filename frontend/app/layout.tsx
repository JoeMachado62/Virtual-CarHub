import "./globals.css";
import type { Metadata } from "next";

import { SiteChrome } from "@/components/SiteChrome";

export const metadata: Metadata = {
  title: "VirtualCarHub",
  description: "AI-first flat-fee virtual dealership built for smarter wholesale buying."
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
