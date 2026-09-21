import type {Metadata} from 'next';
import MarketDashboard from './dashboard';
export const metadata:Metadata={title:'Sage Vista — 大盘',description:'资金流向、机构仓位、客户活动与市场参与度。'};
export default function Market(){return <MarketDashboard/>}
