"use client";

import { useEffect, useState } from "react";

import { adminApi, type AdminSettingOut } from "@/api/client";
import { Cell } from "@/components/ui/cell";
import { Input } from "@/components/ui/input";
import { List } from "@/components/ui/list";
import { Placeholder } from "@/components/ui/placeholder";
import { Section } from "@/components/ui/section";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { useActionError } from "@/components/admin/useActionError";

function SettingRow({ setting, onSaved }: { setting: AdminSettingOut; onSaved: (s: AdminSettingOut) => void }) {
  const { error, run } = useActionError();

  async function save(value: string) {
    await run(async () => {
      onSaved(await adminApi.updateSetting(setting.key, value));
    });
  }

  return (
    <Cell multiline subtitle={setting.description ?? undefined}>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between gap-2">
          <span>{setting.key}</span>
          {setting.type === "bool" ? (
            <Switch checked={setting.value === "true"} onChange={(e) => save(e.target.checked ? "true" : "false")} />
          ) : (
            <Input
              type={setting.type === "int" || setting.type === "float" ? "number" : "text"}
              className="w-[110px]"
              defaultValue={setting.value}
              onBlur={(e) => {
                if (e.target.value !== setting.value) save(e.target.value);
              }}
            />
          )}
        </div>
        {error && <span className="text-[12px] text-red-400">{error}</span>}
      </div>
    </Cell>
  );
}

export default function AdminSettings() {
  const [settings, setSettings] = useState<AdminSettingOut[] | null>(null);

  useEffect(() => {
    adminApi.settings().then(setSettings).catch(() => setSettings([]));
  }, []);

  if (settings === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Настройки">
        {settings.map((s) => (
          <SettingRow
            key={s.key}
            setting={s}
            onSaved={(updated) =>
              setSettings((prev) => prev?.map((x) => (x.key === updated.key ? updated : x)) ?? null)
            }
          />
        ))}
      </Section>
    </List>
  );
}
