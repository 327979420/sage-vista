import {localizedMetadata} from '../../../i18n/server';
import IndustryRadar from './dashboard';
export const generateMetadata=()=>localizedMetadata(
 {title:'Sage Vista — 行业',description:'每日行业速览：行业ETF方向、回调位置与相关候选。'},
 {title:'Sage Vista — Sectors',description:'Daily sector overview: ETF trends, pullbacks and related stock candidates.'}
);
export default function Industry(){return <IndustryRadar/>}
