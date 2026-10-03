// Shadow Self placeholder portrait spec (VMD paper §2.3, R8). Pure data, Node-safe.
import type { Emotion } from "../../contract/types";

export type ShadowHair = "buzz" | "short" | "bob" | "shoulder" | "long" | "bun" | "slicked" | "ponytail" | "twin";
export type ShadowGlasses = "none" | "round" | "square" | "half_rim" | "pushed_up";
export type ShadowAccessory =
  | "tie" | "hairpin" | "pencil" | "bucket_hat" | "headphones" | "headphones_neck"
  | "stethoscope" | "earrings" | "scarf" | "pendant" | "ear_cuff";
/** `default` = an emotion face; `blink` = neutral with closed eyes; `unknown` = glowing "?" (wizard Spec card). */
export type ShadowVariant = "default" | "blink" | "unknown";

export interface ShadowColors {
  primary: string;
  secondary: string;
  accent: string;
  glow: string;
  stage: string;
  surface: string;
}

export interface ShadowSpec {
  colors: ShadowColors;
  emotion: Emotion;
  variant: ShadowVariant;
  hair: ShadowHair;
  glasses: ShadowGlasses;
  accessories: ShadowAccessory[];
  /** Hair streak colour (hex), drawn as a stroke through the hair. */
  streak?: string;
  /** Coat / suit lapels for business, medical, formal, academic outfits. */
  lapels?: boolean;
  /** Shoulder width multiplier (slim 0.92 · average 1 · broad 1.08). */
  shoulders?: number;
  /** Candidate B: mirrored figure. */
  mirror?: boolean;
}
