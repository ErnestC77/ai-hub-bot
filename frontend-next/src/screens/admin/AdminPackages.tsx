"use client";

import { useState, useEffect } from "react";

import { adminApi, type AdminPackageOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import ActionError from "@/components/admin/ActionError";
import { useActionError } from "@/components/admin/useActionError";

export default function AdminPackages() {
  const [packages, setPackages] = useState<AdminPackageOut[] | null>(null);
  const { error, run } = useActionError();

  useEffect(() => {
    adminApi.packages().then(setPackages).catch(() => setPackages([]));
  }, []);

  function applyUpdate(updated: AdminPackageOut) {
    setPackages((prev) => prev?.map((p) => (p.code === updated.code ? updated : p)) ?? null);
  }

  async function updateField(code: string, patch: Partial<Pick<AdminPackageOut, "credits" | "price_rub" | "price_stars">>) {
    await run(async () => {
      applyUpdate(await adminApi.updatePackage(code, patch));
    });
  }

  async function toggle(code: string, isActive: boolean) {
    await run(async () => {
      applyUpdate(await adminApi.updatePackage(code, { is_active: isActive }));
    });
  }

  if (packages === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <ActionError error={error} />
      <Section header="Пакеты">
        {packages.map((p) => (
          <Cell
            key={p.code}
            multiline
            subtitle={p.description ?? undefined}
            after={<Switch checked={p.is_active} onChange={(e) => toggle(p.code, e.target.checked)} />}
          >
            <div className="flex flex-col gap-1.5">
              <span>{p.title}</span>
              <div className="flex flex-wrap gap-1.5">
                <Input
                  header="Кредитов"
                  type="number"
                  className="w-[90px]"
                  defaultValue={p.credits}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== p.credits && value > 0) updateField(p.code, { credits: value });
                  }}
                />
                <Input
                  header="Цена ₽"
                  type="number"
                  className="w-[90px]"
                  defaultValue={p.price_rub}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== p.price_rub && value > 0) updateField(p.code, { price_rub: value });
                  }}
                />
                <Input
                  header="Цена ⭐"
                  type="number"
                  className="w-[90px]"
                  defaultValue={p.price_stars}
                  onBlur={(e) => {
                    const value = Number(e.target.value);
                    if (value !== p.price_stars && value > 0) updateField(p.code, { price_stars: value });
                  }}
                />
              </div>
            </div>
          </Cell>
        ))}
      </Section>
    </List>
  );
}
