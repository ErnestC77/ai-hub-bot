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
  /** Optional photo URLs; when omitted, the design's gradient duo is shown. */
  images?: string[];
  tileWidth?: number;
  tileHeight?: number;
}

export default function ImageStack({ images, tileWidth = 38, tileHeight = 48 }: Props) {
  const tiles: Array<{ key: string; image?: string; gradient?: string }> = images?.length
    ? images.map((src) => ({ key: src, image: src }))
    : DEFAULT_GRADIENTS.map((gradient) => ({ key: gradient, gradient }));

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
