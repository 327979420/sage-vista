import type {Metadata} from 'next';
import MarketDashboard from './dashboard';
export const metadata:Metadata={title:'Sage Vista — 大盘',description:'市场内部参与、成交活跃度与风险温度。'};
export default function Market(){return <MarketDashboard/>}
