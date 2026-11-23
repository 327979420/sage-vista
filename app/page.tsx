import {cookies} from 'next/headers';
import TodayPage from './app/today';
import {localizedMetadata} from './i18n/server';
import {SEEN_COOKIE,seenFrom} from './first-visit';
export const generateMetadata=()=>localizedMetadata({title:'Sage Vista — 今日'},{title:'Sage Vista — Today'});
// A first visit (no seen cookie) opens with the intro hero, rendered on the server so it is the first paint.
export default async function Page(){return <TodayPage intro={!seenFrom((await cookies()).get(SEEN_COOKIE)?.value)}/>}
