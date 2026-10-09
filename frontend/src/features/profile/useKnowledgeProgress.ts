// The latest ingestion stage per knowledge source (Knowledge tab, design D20): an `onGlobal` filter over
// `entity.changed { kind: "knowledge", progress }`, folded by `reduceProgress`. Owner: Builder B.
import { useEffect, useState } from "react";
import { client } from "@/client";
import { reduceProgress, type ProgressMap } from "./knowledge";

export function useKnowledgeProgress(): ProgressMap {
  const [state, setState] = useState<ProgressMap>({});
  useEffect(() => client.onGlobal((e) => setState((s) => reduceProgress(s, e))), []);
  return state;
}
