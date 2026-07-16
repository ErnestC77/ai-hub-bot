export function Progress({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="h-[7px] w-full overflow-hidden rounded-full bg-surface-strong">
      <div
        className="h-full rounded-full bg-[image:var(--brand-gradient)] transition-[width] duration-300"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
