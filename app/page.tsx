import type { Metadata } from "next";
import StockBoard from "./stock-board";
export const metadata: Metadata={title:"Northstar — Quantitative Equity Research",description:"A private, explainable US equity signal board."};
export default function Home(){return <StockBoard/>}
