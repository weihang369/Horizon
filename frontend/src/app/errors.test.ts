// reportError's budget routing (v1 test stage, audit 03-F12): a creation-cap refusal never replaces the figures the
// global `budget.reached` event already put in the Budget reached dialog (O21).
import { afterEach, describe, expect, it } from "vitest";
import { HorizonError } from "../contract/errors";
import { ui } from "../stores/ui";
import { reportError } from "./errors";
import { closeOverlay, openOverlay } from "./layers";

const o21 = () => ui.getState().layers.find((l) => l.id === "O21");

describe("reportError and the Budget reached dialog", () => {
  afterEach(() => closeOverlay("O21"));

  it("keeps the real creation spend when the stream opened the dialog first", () => {
    openOverlay("O21", { scope: "creation", spentUsd: 0.58, capUsd: 0.6 });
    reportError(new HorizonError("creation_budget_exceeded"));
    expect(o21()?.props).toMatchObject({ scope: "creation", spentUsd: 0.58, capUsd: 0.6 });
  });

  it("opens it from the refusal alone, using the figures the error carries", () => {
    reportError(new HorizonError("creation_budget_exceeded", undefined, { details: { spentUsd: 0.61, capUsd: 0.6 } }));
    expect(o21()?.props).toMatchObject({ scope: "creation", spentUsd: 0.61, capUsd: 0.6 });
  });
});
