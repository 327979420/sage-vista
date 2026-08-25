import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sage Vista — Quantitative Equity Research",
  description: "A private, explainable US equity signal board.",
  openGraph: {
    title: "Sage Vista — US Equity Signals",
    description: "Explainable quantitative research for a 1–4 week horizon.",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Sage Vista US Equity Signals",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Sage Vista — US Equity Signals",
    description: "Explainable quantitative research.",
    images: ["/og.png"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <div className="globalnav">
          <a href="/zh/watch/resonance">指标共振</a>
          <a href="/zh/watch/market">ETF温度计</a>
          <a href="/zh/watch">盯盘助手</a>
        </div>
        {children}
      </body>
    </html>
  );
}
