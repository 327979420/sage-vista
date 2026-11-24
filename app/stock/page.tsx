import {localizedMetadata} from '../i18n/server';
import StockLookup from './view';
export const generateMetadata = () => localizedMetadata(
 {title: 'Sage Vista — 查股票', description: '今天 Sage Vista 在约 1,600 只美股里看到了什么，并查任何一只：3W 周线规则、日线形态、多因子。'},
 {title: 'Sage Vista — Stock lookup', description: 'What Sage Vista saw today across about 1,600 US stocks, and a lookup for any one of them: 3W weekly rule, daily setups, multi-factor.'});
export default function Page() { return <StockLookup/>; }
