import type { ReactNode } from "react";

export function List({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-4 px-4 pb-4">{children}</div>;
}
