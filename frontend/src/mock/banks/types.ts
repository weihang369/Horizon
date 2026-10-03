// Bank line shapes. Owner: EE.
import type { Emotion } from "../../contract/types";

export interface BankLine {
  text: string;
  emotion: Emotion;
  /** Keywords scored against the prompt (EE paper §2.3: keyword score, else rotate). */
  tags?: string[];
}

export type BankCategory = "chat" | "scene" | "direction" | "debate";
