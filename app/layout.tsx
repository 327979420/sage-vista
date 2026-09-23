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
  metadataBase: new URL("https://sage.freddyliang.com"),
  title: "Sage Vista — 大盘",
  description: "市场参与、风险温度与个股研究。",
  openGraph: {
    type: "website",
    siteName: "Sage Vista",
    url: "https://sage.freddyliang.com",
    title: "Sage Vista | Daily market insights & stock screening",
    description: "Explore market participation, sector trends and stock setups in one daily dashboard.",
    images: [
      {
        url: "https://sage.freddyliang.com/sage-vista-share-v1.png",
        width: 1200,
        height: 630,
        alt: "Sage Vista with a real English market dashboard snapshot from September 22, 2026.",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Sage Vista | Daily market insights & stock screening",
    description: "Explore market participation, sector trends and stock setups in one daily dashboard.",
    images: ["https://sage.freddyliang.com/sage-vista-share-v1.png"],
  },
  icons: {
    icon: [
      { url: "/favicon.ico?v=sv1", sizes: "16x16 32x32 48x48" },
      { url: "/favicon-32.png?v=sv1", type: "image/png", sizes: "32x32" },
      { url: "/favicon.svg?v=sv1", type: "image/svg+xml", sizes: "any" },
    ],
    shortcut: "/favicon.ico?v=sv1",
    apple: [{ url: "/apple-touch-icon.png?v=sv1", sizes: "180x180" }],
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
