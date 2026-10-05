"use client";
import {useEffect, useState} from 'react';
import {Localized} from './i18n/locale';
import {optedOut, setOptedOut, trackingActive} from './analytics';

// Footer disclosure with a one-click opt-out (also excludes Freddy's own visits).
export default function PrivacyNote() {
 const [active, setActive] = useState(false);
 const [out, setOut] = useState(false);
 // Read tracking state after the first paint so server and client markup still match.
 useEffect(() => {
  const frame = requestAnimationFrame(() => { setActive(trackingActive()); setOut(optedOut()); });
  return () => cancelAnimationFrame(frame);
 }, []);
 const toggle = () => { setOptedOut(!out); setOut(!out); };
 return <Localized><span className="siteFooterPrivacy">PostHog Cookie 用于改进本站{active && <> · <button type="button" aria-pressed={out} onClick={toggle}>{out ? '已退出统计 · 撤销' : '退出统计'}</button></>}</span></Localized>;
}
