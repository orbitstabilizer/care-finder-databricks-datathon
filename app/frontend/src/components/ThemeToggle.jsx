import { useStore } from "../App.jsx";
import { ThemeIcon } from "../icons.jsx";

const NEXT = { auto: "light", light: "dark", dark: "auto" };

export default function ThemeToggle() {
  const { themePref, setThemePref } = useStore();
  const next = NEXT[themePref];
  return (
    <button className="theme-btn" type="button" onClick={() => setThemePref(next)}
      aria-label={`Theme: ${themePref}. Switch to ${next}.`} title={`Theme: ${themePref} (click for ${next})`}>
      <ThemeIcon mode={themePref} />
    </button>
  );
}
