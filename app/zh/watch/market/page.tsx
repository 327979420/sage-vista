import {localizedMetadata} from '../../../i18n/server';
import MarketDashboard from './dashboard';
export const generateMetadata=()=>localizedMetadata(
 {title:'Sage Vista — 大盘',description:'资金流向、机构仓位、客户活动与市场参与度。'},
 {title:'Sage Vista — Market',description:'Fund flows, institutional positioning, investor activity and market participation.'}
);
export default function Market(){return <MarketDashboard/>}
