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
  title: "Northstar — Quantitative Equity Research",
  description: "A private, explainable US equity signal board.",
  openGraph: {
    title: "Northstar — US Equity Signals",
    description: "Explainable quantitative research for a 1–4 week horizon.",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Northstar US Equity Signals",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Northstar — US Equity Signals",
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
          <a href="/zh">中文因子研究</a>
          <a href="/zh/watch">中文盯盘助手</a>
          <a href="/zh/watch/market">ETF温度计</a>
          <a href="/zh/context">环境因子训练</a>
          <a href="/zh/methods">开源系统研究</a>
          <a href="/">Signal board</a>
          <a href="/technical">Technical lab</a>
          <a href="/research">Factor research</a>
          <a href="/efficiency">Trade efficiency</a>
          <a href="/data-quality">Data quality</a>
        </div>
        {children}
      </body>
    </html>
  );
}
