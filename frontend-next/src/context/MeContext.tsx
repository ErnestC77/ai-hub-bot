"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type MeOut } from "@/api/client";

interface MeContextValue {
  me: MeOut | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

const MeContext = createContext<MeContextValue>({
  me: null,
  loading: true,
  refresh: async () => {},
});

export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeOut | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me());
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return <MeContext.Provider value={{ me, loading, refresh }}>{children}</MeContext.Provider>;
}

export function useMe(): MeContextValue {
  return useContext(MeContext);
}
