/* eslint-disable @next/next/no-html-link-for-pages -- vinext beta client routing is broken in the deployed worker; full-page navigation is intentional. */
import type { Metadata } from "next";
import {cookies} from "next/headers";
import {LanguageSwitch, LocaleProvider, Localized} from "./i18n/locale";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./product-v2.css";
import "./market.css";
import "./favorite-pattern.css";
import "./interface.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const UI_VERSION = "UI v6.1";

export const metadata: Metadata = {
  title: "Sage Vista — 大盘",
  description: "市场参与、风险温度与个股研究。",
  openGraph: {
    title: "Sage Vista — 大盘",
    description: "市场、行业、技术机会与多因子证据的可复核研究摘要。",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Sage Vista 大盘",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Sage Vista — 大盘",
    description: "市场、行业、技术机会与多因子证据的可复核研究摘要。",
    images: ["/og.png"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = (await cookies()).get("sv-language")?.value === "en" ? "en" : "zh";
  return (
    <html lang={locale === "en" ? "en" : "zh-CN"}>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <LocaleProvider initialLocale={locale}>
        <div className="siteVersionBar">
          <b>{`Sage Vista ${UI_VERSION}`}</b>
          <div className="siteUtilities"><span>{`Build ${(process.env.GITHUB_SHA ?? "local").slice(0, 7)}`}</span><LanguageSwitch/></div>
        </div>
        <Localized><div className="globalnav">
          <a href="/">今日市场与机会</a>
          <a href="/zh/watch/resonance/rare-opportunities">多因子机会</a>
          <a href="/zh/watch/resonance/favorite-pattern">我最喜欢形态</a>
          <a href="/zh/watch/industry-radar">行业</a>
          <a href="/zh/backtest">回测</a>
        </div></Localized>
        {children}
        </LocaleProvider>
      </body>
    </html>
  );
}
