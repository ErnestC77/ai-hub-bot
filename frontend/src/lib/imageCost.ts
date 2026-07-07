import type { ImageQuality, ImageSize } from "../api/client";

// Зеркалит расчёт стоимости на бэкенде (app/api/routes/chat.py::_compute_image_credit_cost) --
// только для мгновенного отображения цены в UI, реальная стоимость всегда пересчитывается на сервере.
export function computeImageCreditCost(baseCost: number, size: ImageSize, quality: ImageQuality): number {
  let multiplier: number;
  if (size === "square") {
    multiplier = quality === "standard" ? 1 : 2;
  } else {
    multiplier = quality === "standard" ? 2 : 3;
  }
  return Math.max(1, Math.round(baseCost * multiplier));
}
