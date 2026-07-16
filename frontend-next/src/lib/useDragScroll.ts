"use client";

import { useCallback, useRef, type RefObject } from "react";

/**
 * Drag-to-scroll для горизонтальных каруселей. На тач-экране (Telegram) нативный
 * свайп уже работает, а мышью контейнер `overflow-x-auto` со скрытым скроллбаром
 * не потащить -- этот хук добавляет захват мышью.
 *
 * Только мышь: для touch/pen возвращаем управление нативному скроллу (иначе
 * дерёмся с инерцией). Порог в 4px отличает клик от перетаскивания -- после
 * реального drag клик по карточке подавляется (onClickCapture), чтобы не
 * открыть генератор при листании.
 */
export function useDragScroll(ref: RefObject<HTMLElement | null>) {
  const state = useRef({ down: false, startX: 0, startScroll: 0, moved: false });

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return; // тач/перо -> нативный скролл
      const el = ref.current;
      if (!el) return;
      state.current = { down: true, startX: e.clientX, startScroll: el.scrollLeft, moved: false };
    },
    [ref],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const el = ref.current;
      const s = state.current;
      if (!el || !s.down) return;
      const dx = e.clientX - s.startX;
      if (Math.abs(dx) > 4) s.moved = true;
      el.scrollLeft = s.startScroll - dx;
    },
    [ref],
  );

  const endDrag = useCallback(() => {
    state.current.down = false;
  }, []);

  // Клик приходит после mouseup: если только что тащили -- гасим его в фазе
  // capture, чтобы onClick карточки не сработал.
  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (state.current.moved) {
      e.stopPropagation();
      e.preventDefault();
      state.current.moved = false;
    }
  }, []);

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerLeave: endDrag,
    onClickCapture,
  };
}
