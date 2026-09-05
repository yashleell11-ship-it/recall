/**
 * The rich layer: depth, motion, and feedback primitives shared by every
 * screen. Screens import from "@/components/rich" and never reach into the
 * individual files.
 */

export { AnimatedNumber } from "./AnimatedNumber";
export {
  CommandPalette,
  openCommandPalette,
  useCommandKeyLabel,
} from "./CommandPalette";
export { ProgressRing } from "./ProgressRing";
export { Reveal } from "./Reveal";
export { Skeleton, SkeletonText } from "./Skeleton";
export { ToastProvider, useToast } from "./Toast";
export type { ToastFn, ToastOptions, ToastVariant } from "./Toast";
