// #/dev/kit: lazy-loads the VMD's Kit Gallery (Lead gap ruling). Hidden in Presenter Mode. Owner: EE.
import { lazy, Suspense } from "react";
import { usePrefs } from "../../stores/prefs";

const KitGallery = lazy(() => import("./kit/KitGallery").then((m) => ({ default: m.KitGallery })));

export function DevKitRoute() {
  const presenter = usePrefs((p) => p.presenterMode);
  if (presenter) return <main style={{ padding: 48 }}>The Kit Gallery is hidden in Presenter Mode.</main>;
  return (
    <Suspense fallback={<main style={{ padding: 48 }} aria-busy="true">Loading Kit Gallery…</main>}>
      <KitGallery />
    </Suspense>
  );
}
