// App shell: route host, ambient chrome, LayerStack, toasts, the one TransitionLayer, dev overlays. Owner: EE.
import { Suspense } from "react";
import { useSettings } from "../client/hooks";
import { CommitCounter, PerfHUD } from "../features/dev/PerfHUD";
import { JobPill } from "../features/profile/JobPill";
import { DemoTape } from "../features/shell/DemoTape";
import { DesktopGuard } from "../features/shell/DesktopGuard";
import { MiniPlayer } from "../features/shell/MiniPlayer";
import { TransitionLayer } from "../motion/TransitionLayer";
import { useRoute } from "../router";
import type { Route } from "../router";
import { useMock } from "../stores/mock";
import { usePrefs } from "../stores/prefs";
import { useUi } from "../stores/ui";
import { LayerStack } from "./LayerStack";
import { useAppBoot, useDesktopGuard } from "./providers";
import { ROUTES, routeKey } from "./routes";
import { ToastHost } from "./ToastHost";
import s from "./App.module.css";

function RouteView({ route }: { route: Route }) {
  const Screen = ROUTES[route.name] as unknown as React.ComponentType<{ route: Route }>;
  return (
    <Suspense fallback={<div className={s.loading} aria-busy="true">LOADING</div>}>
      <Screen key={routeKey(route)} route={route} />
    </Suspense>
  );
}

export function App() {
  useAppBoot();
  const route = useRoute();
  const settings = useSettings().data;
  const small = useDesktopGuard();
  const presenter = usePrefs((p) => p.presenterMode);
  const perf = useUi((u) => u.perfHud);
  const speed = useMock((m) => m.speed);
  const demo = settings?.demoMode ?? false;
  const chrome = route.name !== "title" && route.name !== "dev";
  return (
    <CommitCounter>
      <div className={s.app} data-route={route.name}>
        {demo && chrome && <div className={s.ambientTop}><DemoTape /></div>}
        <div className={s.screen}>
          <RouteView route={route} />
        </div>
        {chrome && <MiniPlayer />}
        {chrome && <JobPill />}
        <LayerStack />
        <ToastHost />
        <TransitionLayer />
        {speed > 1 && <div className={s.speedBadge} aria-label={`Demo speed ×${speed}`}>×{speed}</div>}
        {import.meta.env.DEV && perf && !presenter && <PerfHUD />}
        {small && <DesktopGuard />}
      </div>
    </CommitCounter>
  );
}
