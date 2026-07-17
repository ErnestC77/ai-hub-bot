"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type MeOut } from "@/api/client";

interface MeContextValue {
  me: MeOut | null;
  loading: boolean;
  /** true, если последняя загрузка профиля завершилась ошибкой (сеть/401);
   *  сбрасывается при повторном refresh() — ошибка не «залипает». */
  error: boolean;
  refresh: () => Promise<void>;
}

const MeContext = createContext<MeContextValue>({
  me: null,
  loading: true,
  error: false,
  refresh: async () => {},
});

export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    setError(false);
    try {
      setMe(await api.me());
    } catch {
      setMe(null);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount is intentional here, not derived-state — the rule's cascading-render
    // concern doesn't apply to a single top-level effect with an empty/stable dep array.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  return <MeContext.Provider value={{ me, loading, error, refresh }}>{children}</MeContext.Provider>;
}

export function useMe(): MeContextValue {
  return useContext(MeContext);
}
