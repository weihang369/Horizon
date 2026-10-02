// Shadow Self placeholder portraits (R8). Everything here is pure and Node-safe.
export * from "./types";
export { renderShadowSvg, shadowDataUrl } from "./renderShadowSvg";
export {
  specFromAppearance,
  identityFromAppearance,
  placeholderPortraitPath,
  isPlaceholderUrl,
  SEED_IDENTITIES,
  type SpecOptions,
} from "./specFromAppearance";
