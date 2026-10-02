// O14 Toast stack host (STATE-05): renders the VMD ToastView frames, top-right under the mini-player. Owner: EE.
import { useUi } from "../stores/ui";
import { ToastView } from "../ui/Panels";
import { dismissToast } from "./layers";
import s from "./App.module.css";

export function ToastHost() {
  const toasts = useUi((u) => u.toasts);
  return (
    <div className={s.toasts} aria-live="polite">
      {toasts.map((t) => (
        <ToastView
          key={t.id}
          variant={t.variant}
          text={t.text}
          action={t.action ? { label: t.action.label, run: () => { t.action!.run(); dismissToast(t.id); } } : undefined}
          onDismiss={() => dismissToast(t.id)}
        />
      ))}
    </div>
  );
}
