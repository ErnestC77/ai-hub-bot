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
    <div style={{ position: "relative", width, height }}>
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
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              borderRadius: 16,
              border: "3px solid var(--bg-deep)",
              boxShadow: isFront ? "0 10px 24px rgba(0,0,0,0.45)" : "0 4px 12px rgba(0,0,0,0.3)",
              transform: `translate(${offset.x}px, ${offset.y}px) rotate(${rotate}deg)`,
              zIndex: i,
            }}
          />
        );
      })}
    </div>
  );
}
