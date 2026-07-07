"use client";

import { Button } from "@/components/ui/button";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-8 text-center">
      <h1 className="heading-font text-xl font-bold text-foreground">Что-то пошло не так</h1>
      <p className="text-sm text-foreground-muted">Попробуйте ещё раз.</p>
      <Button onClick={reset}>Повторить</Button>
    </div>
  );
}
