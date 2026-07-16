"use client";

import { useRef, type ReactNode } from "react";

import { useDragScroll } from "@/lib/useDragScroll";

interface Props {
  className?: string;
  children: ReactNode;
  "data-testid"?: string;
}

/**
 * Горизонтальный скролл-контейнер с drag-to-scroll мышью (см. useDragScroll).
 * Классы раскладки передаёт вызывающий -- компонент только добавляет захват.
 */
export default function DragScroll({ className, children, ...rest }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const handlers = useDragScroll(ref);
  return (
    <div ref={ref} className={className} {...handlers} {...rest}>
      {children}
    </div>
  );
}
