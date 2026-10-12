import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import "./globals.css";

const plex = IBM_Plex_Sans({ variable: "--font-plex", subsets: ["latin"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });
const sourceSerif = Source_Serif_4({ variable: "--font-source-serif", subsets: ["latin"], style: ["normal", "italic"] });

const DESCRIPTION = "Find where your policy can't run in your organization, with the lines that prove it.";

export const metadata: Metadata = {
  metadataBase: new URL("https://orgflowai.web.app"),
  title: "OrgFlow",
  description: DESCRIPTION,
  openGraph: {
    title: "OrgFlow: stop requests from getting stuck between departments",
    description: DESCRIPTION,
    url: "/",
    siteName: "OrgFlow",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "OrgFlow's map of a company's departments and the places a case stops" }],
    type: "website",
  },
  twitter: { card: "summary_large_image", title: "OrgFlow", description: DESCRIPTION, images: ["/og.png"] },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plex.variable} ${plexMono.variable} ${sourceSerif.variable} antialiased`}>
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
