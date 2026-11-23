import {permanentRedirect} from 'next/navigation';

// Old address, kept so shared links (Discord, bookmarks) still work.
export default function Page(){permanentRedirect('/market')}
