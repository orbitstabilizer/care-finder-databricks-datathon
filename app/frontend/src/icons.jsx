const P = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
export const Warn = ({ s = 13 }) => (<svg viewBox="0 0 24 24" width={s} height={s} aria-hidden="true"><path {...P} d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></svg>);
export const Phone = () => (<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path {...P} d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z" /></svg>);
export const Nav = () => (<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path {...P} d="m3 11 19-9-9 19-2-8-8-2Z" /></svg>);
export const Web = () => (<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path {...P} d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm-10-10h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z" /></svg>);
export const Back = () => (<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path {...P} d="M19 12H5m7 7-7-7 7-7" /></svg>);
export const Pin = () => (<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path {...P} strokeWidth={1.8} d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12Zm0-9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" /></svg>);
export const Search = () => (<svg className="hero-ico" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path {...P} d="m21 21-4.3-4.3M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" /></svg>);
export const Chev = () => (<svg className="chev" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path {...P} d="m6 9 6 6 6-6" /></svg>);
export const Cursor = () => (<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path {...P} d="M9 9l10 4-4 2-2 4-4-10Z M4 4l2 2" /></svg>);
export const Close = () => (<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path {...P} d="M6 6l12 12M18 6 6 18" /></svg>);
export const Logo = () => (<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Zm1 10.5h-2v-2.5H8.5V8H11V5.5h2V8h2.5v2H13v2.5Z" /></svg>);
export const ThemeIcon = ({ mode }) => {
  if (mode === "light") return (<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><g {...P}><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></g></svg>);
  if (mode === "dark") return (<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path {...P} d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" /></svg>);
  return (<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="2" /><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" /></svg>);
};
