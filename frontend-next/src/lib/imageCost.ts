import type { ImageAspect, ImageResolution } from "@/api/client";

const ASPECT_TO_BUCKET: Record<ImageAspect, "square" | "landscape" | "portrait"> = {
  auto: "square",
  "1:1": "square",
  "4:3": "square",
  "4:5": "square",
  "5:4": "square",
  "3:2": "landscape",
  "16:9": "landscape",
  "21:9": "landscape",
  "2:3": "portrait",
  "3:4": "portrait",
  "9:16": "portrait",
};

const COST_MULTIPLIER: Record<string, number> = {
  "square:1k": 1,
  "square:2k": 2,
  "square:4k": 3,
  "landscape:1k": 2,
  "landscape:2k": 3,
  "landscape:4k": 4,
  "portrait:1k": 2,
  "portrait:2k": 3,
  "portrait:4k": 4,
};

export function computeImageCreditCost(baseCost: number, aspect: ImageAspect, resolution: ImageResolution): number {
  const bucket = ASPECT_TO_BUCKET[aspect] ?? "square";
  const multiplier = COST_MULTIPLIER[`${bucket}:${resolution}`] ?? 1;
  return Math.max(1, Math.round(baseCost * multiplier));
}
