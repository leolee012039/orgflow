import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import "./globals.css";

const plex = IBM_Plex_Sans({ variable: "--font-plex", subsets: ["latin"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });
const sourceSerif = Source_Serif_4({ variable: "--font-source-serif", subsets: ["latin"], style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: "OrgFlow",
  description: "Find where your policy can't run in your organization, with the lines that prove it.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plex.variable} ${plexMono.variable} ${sourceSerif.variable} antialiased`}>
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
