import {localizedMetadata} from '../../../../i18n/server';
import {TrackerShell} from "../tracker-ui";
import AboutContent from "./content";
import {AboutHead,AboutFlow} from "../../../../app/research-heads";
import MoreDetails from "../../../../app/more-details";

export const generateMetadata=()=>localizedMetadata(
 {title:'Sage Vista — 关于 SV',description:'三重滤网式的顺势回调交易系统：SV 是什么、如何运作、如何使用。'},
 {title:'Sage Vista — About SV',description:'A Triple Screen–style trend-pullback trading system: what SV is, how it works and how to use it.'}
);

export default function About(){
 return <TrackerShell active="功能介绍" title="关于 Sage Vista" subtitle="三重滤网式的顺势回调系统。" overview><AboutHead/><AboutFlow/><MoreDetails zh="完整说明（SV 是什么、怎么用、每种方法）" en="Full guide (what SV is, how to use it, each method)"><AboutContent/></MoreDetails></TrackerShell>;
}
