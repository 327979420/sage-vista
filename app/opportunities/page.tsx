import {localizedMetadata} from '../i18n/server';
import ComingSoon from '../coming-soon';
import {strings as s} from '../app/strings';
export const generateMetadata=()=>localizedMetadata({title:'Sage Vista — 3W 机会'},{title:'Sage Vista — 3W Opportunities'});
export default function Page() {return <ComingSoon title={s.opportunities}/>}
