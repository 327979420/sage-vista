import type { Metadata } from "next";
import {requestLocale} from './i18n/server';
import {LocaleProvider} from "./i18n/locale";
import {NavigationCountProvider} from './navigation-count';
import SiteNavigation from './site-navigation';
import SiteFooter from "./site-footer";
import Tour from "./tour";
import Analytics from "./analytics";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./product-v2.css";
import "./market.css";
import "./favorite-pattern.css";
import "./interface.css";
import "./multifactor.css";
import "./app/style.css";
import "./evidence/style.css";
// Dark terminal look: generated recolouring of the styles above, then the shell itself.
import "./dark-theme.css";
import "./terminal.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const UI_VERSION = "UI v7.0";

export const metadata: Metadata = {
  metadataBase: new URL("https://sage.freddyliang.com"),
  title: "Sage Vista — Market",
  description: "Market participation, risk conditions and stock research.",
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
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await requestLocale();
  return (
    <html lang={locale === "en" ? "en" : "zh-CN"} className="svDark">
      <head>
        {/* Keep bitmap icons in the initial head even when localized metadata streams. */}
        <link rel="icon" href="/brand/sv-v2/icon-16.png" type="image/png" sizes="16x16" />
        <link rel="icon" href="/brand/sv-v2/icon-32.png" type="image/png" sizes="32x32" />
        <link rel="shortcut icon" href="/brand/sv-v2/favicon.ico" />
        <link rel="apple-touch-icon" href="/brand/sv-v2/apple-touch-icon.png" sizes="180x180" />
        {/* vinext metadata currently omits the mask icon's color attribute. */}
        <link rel="mask-icon" href="/brand/sv-v2/pinned-tab.svg" color="#19293f" />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <LocaleProvider initialLocale={locale}>
        <NavigationCountProvider><div className="svShell">
        <SiteNavigation uiVersion={UI_VERSION} build={(process.env.GITHUB_SHA ?? "local").slice(0, 7)}/>
        <div className="svMain">{children}<SiteFooter/></div>
        </div></NavigationCountProvider>
        <Tour/>
        <Analytics/>
        </LocaleProvider>
      </body>
    </html>
  );
}
