"use client";

import { Button } from "@/components/ui/button";

export default function LoginFailedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-8 text-center">
      <h1 className="heading-font text-xl font-bold text-foreground">Не удалось войти</h1>
      <p className="text-sm text-foreground-muted">Сессия истекла или вход не удался. Перезапустите приложение.</p>
      <Button onClick={() => window.location.reload()}>Перезапустить</Button>
    </div>
  );
}
