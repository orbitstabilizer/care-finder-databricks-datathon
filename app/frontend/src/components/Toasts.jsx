import { useStore } from "../App.jsx";

export default function Toasts() {
  const { toasts, setToasts } = useStore();
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span>{t.text}</span>
          <button className="t-x" aria-label="Dismiss" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>&times;</button>
        </div>
      ))}
    </div>
  );
}
