import {localizedMetadata} from '../i18n/server';
import ComingSoon from '../coming-soon';
import {strings as s} from '../app/strings';
export const generateMetadata=()=>localizedMetadata({title:'Sage Vista — 成绩单'},{title:'Sage Vista — Scorecard'});
export default function Page() {return <ComingSoon title={s.record}/>}
