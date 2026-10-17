import {Localized} from './i18n/locale';
import {strings as s} from './app/strings';
export default function ComingSoon({title}:{title:string}) {
 return <Localized><main className="rtPage rtFeaturedPage cockpit marketSummaryPage svApp"><header className="rtSubHero"><div><p>SAGE VISTA</p><h1>{title}</h1></div></header><div className="cockpitEmpty" role="status"><strong>{s.soon}</strong></div></main></Localized>;
}
