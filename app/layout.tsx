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
        <div className="globalnav">
          <a href="/">今日研究总览</a>
          <a href="/zh/watch/resonance/macd">指标共振</a>
          <a href="/zh/watch/resonance/rare-opportunities">多因子</a>
          <a href="/zh/watch/industry-radar">行业雷达</a>
          <a href="/zh/watch/resonance/research">研究 / 实验</a>
        </div>
        {children}
      </body>
    </html>
  );
}
