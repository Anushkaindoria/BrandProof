import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BrandProof AI · Trusted Content. Stronger Brands.",
  description: "Evidence-backed brand governance for every piece of content.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
