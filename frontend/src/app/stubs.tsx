// Foundation stubs: every screen/overlay renders its id and name until its builder replaces it. Owner: EE.
import type { ReactNode } from "react";
import { back, navigate } from "../router";
import type { Route } from "../router";
import { Button } from "../ui/Button";
import { Drawer, Modal } from "../ui/Panels";
import { Tape } from "../ui/Tape";
import type { OverlayBaseProps, OverlayId } from "./overlayTypes";
import { OVERLAY_KINDS, OVERLAY_NAMES } from "./overlayTypes";
import s from "./App.module.css";

export interface StubLink { label: string; to: Route }

export function StubScreen({ id, name, owner, links = [], children }: { id: string; name: string; owner: string; links?: StubLink[]; children?: ReactNode }) {
  return (
    <main className={s.stub} data-screen={id}>
      <Tape tone="brand" size="md">{id} · STUB · {owner}</Tape>
      <h1 className={s.stubTitle}>{name}</h1>
      {children}
      <nav className={s.stubLinks}>
        <Button variant="ghost" size="sm" onClick={() => back()}>◂ Back</Button>
        {links.map((l) => (
          <Button key={l.label} variant="secondary" size="sm" onClick={() => navigate(l.to)}>{l.label}</Button>
        ))}
      </nav>
    </main>
  );
}

export function StubOverlay({ id, close, children }: { id: OverlayId; children?: ReactNode } & Pick<OverlayBaseProps, "close">) {
  const title = `${id} · ${OVERLAY_NAMES[id]}`;
  if (OVERLAY_KINDS[id] === "drawer") {
    return (
      <Drawer title={title} onClose={close}>
        <p className={s.stubNote}>Stub. The builder replaces this overlay.</p>
        {children}
      </Drawer>
    );
  }
  return (
    <Modal title={title} tape="STUB" onClose={close} actions={<Button size="sm" onClick={close}>Close</Button>}>
      <p className={s.stubNote}>Stub. The builder replaces this overlay.</p>
      {children}
    </Modal>
  );
}
