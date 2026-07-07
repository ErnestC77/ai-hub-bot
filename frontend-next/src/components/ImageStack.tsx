import { cn } from "@/lib/cn";

interface Props {
  images: string[];
  width?: number;
  height?: number;
}

const ROTATIONS = [-10, 7, 0];
const OFFSETS = [
  { x: -10, y: 4 },
  { x: 6, y: -2 },
  { x: 0, y: 0 },
];

export default function ImageStack({ images, width = 104, height = 132 }: Props) {
  return (
    <div className="relative" style={{ width, height }}>
      {images.map((src, i) => {
        const rotate = ROTATIONS[i] ?? 0;
        const offset = OFFSETS[i] ?? { x: 0, y: 0 };
        const isFront = i === images.length - 1;
        return (
          <img
            key={src}
            src={src}
            alt=""
            loading="lazy"
            className={cn(
              "absolute inset-0 h-full w-full rounded-[16px] border-[3px] border-bg-deep object-cover",
              isFront ? "shadow-[0_10px_24px_rgba(0,0,0,0.45)]" : "shadow-[0_4px_12px_rgba(0,0,0,0.3)]",
            )}
            style={{
              transform: `translate(${offset.x}px, ${offset.y}px) rotate(${rotate}deg)`,
              zIndex: i,
            }}
          />
        );
      })}
    </div>
  );
}
