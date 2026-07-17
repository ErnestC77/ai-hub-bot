/**
 * Aurora Glass overlapping tile stack (design 3a, «Сгенерировать фото» card):
 * small rounded tiles with a dark seam border, each next tile tucked under
 * the previous one. Renders gradient tiles by default; pass `images` to show
 * photo previews instead.
 */

const DEFAULT_GRADIENTS = [
  "linear-gradient(160deg,#7c5cff,#3b2b8f)",
  "linear-gradient(160deg,#35e0e6,#1b7f9c)",
];

interface Props {
  /**
   * Optional photo URLs, filling tiles from the front. Fewer images than the
   * gradient duo keeps the remaining tiles as gradients (so the design's stack
   * survives a single preview); more images simply add tiles. The gradient also
   * stays behind each photo, so a failed load degrades to the original look.
   */
  images?: string[];
  tileWidth?: number;
  tileHeight?: number;
}

export default function ImageStack({ images, tileWidth = 38, tileHeight = 48 }: Props) {
  const tileCount = Math.max(DEFAULT_GRADIENTS.length, images?.length ?? 0);
  // Плитки перекрываются, и поздние рисуются поверх ранних -- значит передняя
  // плитка это последняя. Фото раскладываем с конца, иначе градиент накрывает их.
  const firstPhoto = tileCount - (images?.length ?? 0);
  const tiles = Array.from({ length: tileCount }, (_, i) => ({
    key: images?.[i - firstPhoto] ?? `gradient-${i}`,
    image: i >= firstPhoto ? images?.[i - firstPhoto] : undefined,
    gradient: DEFAULT_GRADIENTS[i % DEFAULT_GRADIENTS.length],
  }));

  return (
    <div className="flex" aria-hidden>
      {tiles.map((tile, i) => (
        <div
          key={tile.key}
          className="overflow-hidden rounded-[11px] border-2 border-[#140c26]"
          style={{
            width: tileWidth,
            height: tileHeight,
            marginLeft: i === 0 ? 0 : -16,
            background: tile.gradient,
          }}
        >
          {tile.image && (
            <img src={tile.image} alt="" loading="lazy" className="h-full w-full object-cover" />
          )}
        </div>
      ))}
    </div>
  );
}
