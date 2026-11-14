'use client';
import type {ReactNode} from 'react';
import {Localized,useLocale} from '../i18n/locale';

// Redesigned pages lead with the terminal view; the original page stays one click away.
// Localized here, because translation does not reach into a custom component's children.
export default function MoreDetails({zh,en,children}:{zh:string;en:string;children:ReactNode}) {
 const {locale}=useLocale();
 return <details className="ovMore"><summary>{locale==='en'?en:zh}</summary><Localized>{children}</Localized></details>;
}
