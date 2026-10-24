// Shared 24px outline icons, matching the site's existing navigation.
export const navigationIcons=[
 'M3 17V7m6 10V3m6 14v-6m6 6V5',
 'M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9zM19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z',
 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
 'M4 4v16h17M8 15l4-5 4 2 5-7',
 'm3 16 4-7 5 8 5-12 4 5',
 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
 'M4 5a2 2 0 0 1 2-2h5v17H6a2 2 0 0 0-2 2zM20 5a2 2 0 0 0-2-2h-5v17h5a2 2 0 0 1 2 2z',
];
export const stepIcons = {
 signal: navigationIcons[1],
 fill: 'M9 3H5v18h14V3h-4M9 3h6v4H9zM8 14l3 3 5-6',
 exit: 'M10 4H4v16h6M10 12h11m-4-4 4 4-4 4',
 target: 'M12 20V4m-6 6 6-6 6 6',
 stop: 'M12 4v16m-6-6 6 6 6-6',
 time: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2',
 result: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8',
};
export function SiteIcon({path}:{path:string}) {
 return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={path}/></svg>;
}
