"use client";

import { useCallback, useState } from "react";

/**
 * Обёртка write-действий админки: ловит ошибку в error-стейт вместо тихого
 * unhandled-rejection. Раньше `try/finally` без catch давал молчаливый провал --
 * админ думал, что заблокировал/начислил/сохранил, а операция упала.
 *
 *   const { error, run } = useActionError();
 *   run(async () => { const u = await adminApi.blockUser(id); onSaved(u); });
 *   ...<ActionError error={error} />
 */
export function useActionError() {
  const [error, setError] = useState("");

  const run = useCallback(async (fn: () => Promise<void>) => {
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось выполнить операцию");
    }
  }, []);

  return { error, run };
}
