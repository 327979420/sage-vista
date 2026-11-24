import {localizedMetadata} from '../../i18n/server';
import StockLookup from '../view';

// One address per stock (/stock/NVDA) so a lookup can be shared and found by search engines.
type Props = {params: Promise<{symbol: string}> | {symbol: string}};
const symbolOf = async (params: Props['params']) => {
 const raw = (await params).symbol;
 let value = raw;
 try { value = decodeURIComponent(raw); } catch { /* keep the raw segment */ }
 return value.trim().slice(0, 16);
};

export async function generateMetadata({params}: Props) {
 const s = (await symbolOf(params)).toUpperCase();
 return localizedMetadata(
  {title: `${s} · Sage Vista 查股票`, description: `Sage Vista 今天怎么看 ${s}：3W 周线规则、日线形态和多因子。规则的判断，不是投资建议。`},
  {title: `${s} · Sage Vista stock lookup`, description: `What Sage Vista's rules say about ${s} today: 3W weekly rule, daily setups and multi-factor. Not investment advice.`});
}

export default async function Page({params}: Props) {
 return <StockLookup symbol={await symbolOf(params)}/>;
}
