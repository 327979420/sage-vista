import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./product-v2.css";
import "./home-v3.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const UI_VERSION = "UI v3.1";

export const metadata: Metadata = {
  title: "Sage Vista — 今日研究总览",
  description: "市场、行业、技术机会与多因子证据的每日研究摘要。",
  openGraph: {
    title: "Sage Vista — 今日研究总览",
    description: "市场、行业、技术机会与多因子证据的可复核研究摘要。",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Sage Vista 今日研究总览",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Sage Vista — 今日研究总览",
    description: "市场、行业、技术机会与多因子证据的可复核研究摘要。",
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
        <div className="siteVersionBar">
          <b>{`Sage Vista ${UI_VERSION}`}</b>
          <span>{`Build ${(process.env.GITHUB_SHA ?? "local").slice(0, 7)}`}</span>
        </div>
        <div className="globalnav">
          <a href="/">今日市场与机会</a>
          <a href="/zh/watch/resonance/macd">个股研究</a>
          <a href="/zh/watch/resonance/rare-opportunities">多因子机会</a>
          <a href="/zh/watch/industry-radar">行业与大盘</a>
          <a href="/zh/watch/resonance/research">历史与实验</a>
        </div>
        {children}
      </body>
    </html>
  );
}
