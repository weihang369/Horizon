// Settings → Connection (SET-01, APP-09): masked key with Show/Hide, Save, Test connection (✓ / ✗ with reason), Clear.
// After saving only `sk-or-…a1b2` is shown. Mock: any `sk-or-*` is valid, `sk-or-bad*` invalid (R15). Owner: Builder A.
import { useState } from "react";
import { openOverlay, toast } from "../../app/layers";
import { client } from "../../client";
import type { ConnectionResult } from "../../client/HorizonClient";
import type { HorizonErrorShape } from "../../contract/errors";
import type { AppSettings } from "../../contract/types";
import { formatUsd } from "../../domain/format";
import { Button } from "../../ui/Button";
import { TextField } from "../../ui/Fields";
import { ErrorTape } from "../../ui/Panels";
import { Tape } from "../../ui/Tape";
import { CheckIcon, KeyIcon } from "../../ui/icons";
import { maskKey, readKeyHint, saveKeyHint } from "../shell/keyHint";
import { Row, Section } from "./parts";
import s from "./Settings.module.css";

type TestState = { kind: "idle" } | { kind: "busy" } | { kind: "ok"; r: ConnectionResult } | { kind: "fail"; message: string; code?: string };

export function ConnectionTab({ settings }: { settings: AppSettings }) {
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [test, setTest] = useState<TestState>({ kind: "idle" });
  const [hint, setHint] = useState(readKeyHint);
  const status = settings.openRouterKeyStatus;

  const save = async () => {
    const k = key.trim();
    if (!k) return setError("Paste a key first.");
    if (!k.startsWith("sk-or-")) return setError("OpenRouter keys start with sk-or-.");
    setBusy(true);
    setError(null);
    try {
      const next = await client.settings.setKey(k);
      saveKeyHint(k);
      setHint(readKeyHint());
      setKey("");
      setTest({ kind: "idle" });
      if (next.openRouterKeyStatus === "invalid") setError("That key was rejected by OpenRouter.");
      else toast({ variant: "success", text: "Key saved on this machine. Demo mode is off." });
    } catch (e) {
      setError((e as HorizonErrorShape)?.message ?? "Couldn't save the key.");
    } finally {
      setBusy(false);
    }
  };
  const clear = async () => {
    await client.settings.setKey(null);
    saveKeyHint(null);
    setHint(null);
    setTest({ kind: "idle" });
    toast({ variant: "info", text: "Key cleared. Back to demo mode." });
  };
  const runTest = async () => {
    if (status === "missing") {
      openOverlay("O05", { reason: "Testing the connection needs a key. Paste one above first." });
      return;
    }
    setTest({ kind: "busy" });
    try {
      setTest({ kind: "ok", r: await client.settings.testConnection() });
    } catch (e) {
      const err = e as HorizonErrorShape;
      setTest({ kind: "fail", message: err?.message ?? "Connection failed.", code: err?.code });
    }
  };

  return (
    <>
      <div className={s.status} data-status={status}>
        {status === "set" ? (
          <>
            <Tape tone="ok" size="md"><CheckIcon /> KEY SET</Tape>
            <span className={s.statusKey}>{maskKey(hint)}</span>
            <span className={s.statusText}>Live mode: chat, create and start sessions.</span>
          </>
        ) : status === "invalid" ? (
          <>
            <Tape tone="error" size="md">KEY REJECTED</Tape>
            <span className={s.statusKey}>{maskKey(hint)}</span>
            <span className={s.statusText}>OpenRouter rejected this key. Paste a new one.</span>
          </>
        ) : (
          <>
            <Tape tone="brand" size="md">DEMO MODE</Tape>
            <span className={s.statusText}>Browsing seed data. Add your OpenRouter key to chat &amp; create.</span>
          </>
        )}
      </div>

      <Section title="OpenRouter key" desc={<>Stored on this machine only, never in the repo. Get one at <a className={s.link} href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">openrouter.ai/keys ↗</a></>}>
        <form className={s.keyRow} onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <TextField
            label={status === "missing" ? "Key" : "Replace key"}
            type={show ? "text" : "password"}
            value={key}
            placeholder={status === "missing" ? "sk-or-…" : maskKey(hint)}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => { setKey(e.target.value); setError(null); }}
            error={error}
          />
          <div className={s.keyBtns}>
            <Button type="button" variant="ghost" size="sm" aria-pressed={show} onClick={() => setShow((v) => !v)}>{show ? "Hide" : "Show"}</Button>
            <Button type="submit" icon={<KeyIcon />} disabled={busy}>{busy ? "Saving…" : "Save key"}</Button>
          </div>
        </form>
      </Section>

      <Section title="Check it">
        <Row label="Test connection" desc="Pings OpenRouter with your key and reports latency and balance.">
          <Button variant="secondary" keyLocked={status === "missing"} disabled={test.kind === "busy"} onClick={() => void runTest()}>
            {test.kind === "busy" ? "Testing…" : "Test connection"}
          </Button>
        </Row>
        {test.kind === "ok" && (
          <p className={s.testOk} role="status"><CheckIcon /> Connected · {test.r.latencyMs} ms{test.r.creditsUsd !== undefined ? ` · balance ${formatUsd(test.r.creditsUsd)}` : ""}</p>
        )}
        {test.kind === "fail" && <ErrorTape message={test.message} code={test.code} action={{ label: "Retry", run: () => void runTest() }} />}
        {status !== "missing" && (
          <Row label="Clear key" desc="Removes the key and returns to demo mode. Recordings stay.">
            <Button variant="ghost" onClick={() => void clear()}>Clear key</Button>
          </Row>
        )}
      </Section>
    </>
  );
}
