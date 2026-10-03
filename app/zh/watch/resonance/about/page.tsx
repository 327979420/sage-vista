import {localizedMetadata} from '../../../../i18n/server';
import {TrackerShell} from "../tracker-ui";
import AboutContent from "./content";

export const generateMetadata=()=>localizedMetadata(
 {title:'Sage Vista — 关于 SV',description:'三重滤网式的顺势回调交易系统：SV 是什么、如何运作、如何使用。'},
 {title:'Sage Vista — About SV',description:'A Triple Screen–style trend-pullback trading system: what SV is, how it works and how to use it.'}
);

export default function About(){
 return <TrackerShell active="功能介绍" title="关于 Sage Vista" subtitle="三重滤网式的顺势回调系统。"><AboutContent/></TrackerShell>;
}
