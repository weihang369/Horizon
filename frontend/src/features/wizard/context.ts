// Wizard context shared by the step components. Owner: Builder B.
import { createContext, useContext } from "react";
import type { Character, CreationStep, World } from "@/contract/types";
import type { GateFacts } from "./gates";
import type { useCharacterJobs } from "./generate";
import type { WorkingApi } from "./working";

export interface WizardCtx {
  worldId: string;
  world?: World;
  character: Character | null;
  step: CreationStep;
  edit: boolean;
  work: WorkingApi;
  jobs: ReturnType<typeof useCharacterJobs>;
  facts: GateFacts;
  /** Persist working edits (and creationStep for drafts). Resolves false on failure. */
  save(opts?: { step?: CreationStep; quiet?: boolean }): Promise<boolean>;
  /** Save, then move to a step (replace navigation, no wipe: the work area animates locally). */
  goStep(step: CreationStep, opts?: { skipSave?: boolean }): Promise<void>;
  /** Leave the wizard (to the profile when editing, else the hub). Runs the leave guard. */
  exit(): void;
}

export const WizardContext = createContext<WizardCtx | null>(null);

export function useWizard(): WizardCtx {
  const v = useContext(WizardContext);
  if (!v) throw new Error("useWizard outside WizardScreen");
  return v;
}
