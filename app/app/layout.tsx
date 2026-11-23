import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Is my train running?",
  description: "Next Rodalies de Catalunya trains between two stations, with live status, a plan B and a live map.",
  // no favicon: an empty icon also stops the browser asking for /favicon.ico
  icons: { icon: "data:," },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
