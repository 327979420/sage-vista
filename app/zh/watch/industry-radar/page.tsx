import type {Metadata} from 'next';
import IndustryRadar from './dashboard';
export const metadata:Metadata={title:'Sage Vista — 行业',description:'每日行业速览：行业ETF方向、回调位置与相关候选。'};
export default function Industry(){return <IndustryRadar/>}
