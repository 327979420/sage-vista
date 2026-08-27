import type { Metadata } from "next";
import Overview from "./zh/watch/resonance/page";
export const metadata: Metadata={title:"Sage Vista — 今日研究总览",description:"市场、行业、技术机会与多因子证据的每日研究摘要。"};
export default function Home(){return <Overview/>}
