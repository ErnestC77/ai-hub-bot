import { useEffect, useState } from "react";
import { Button, Cell, Input, List, Placeholder, Section, Select, Spinner, Switch } from "@telegram-apps/telegram-ui";

import { adminApi, type AdminBannerOut, type BannerWriteFields } from "../../api/client";

const EMPTY_FORM: BannerWriteFields = {
  title: "",
  subtitle: "",
  badge_text: "",
  cta_text: "Открыть",
  image_url: "",
  action_type: "prompt",
  action_value: "",
  sort_order: 0,
  is_active: true,
};

export default function AdminBanners() {
  const [banners, setBanners] = useState<AdminBannerOut[] | null>(null);
  const [form, setForm] = useState<BannerWriteFields>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);

  function load() {
    adminApi.banners().then(setBanners).catch(() => setBanners([]));
  }

  useEffect(load, []);

  async function toggleActive(banner: AdminBannerOut) {
    const updated = await adminApi.updateBanner(banner.id, { is_active: !banner.is_active });
    setBanners((prev) => prev?.map((b) => (b.id === banner.id ? updated : b)) ?? null);
  }

  async function remove(banner: AdminBannerOut) {
    await adminApi.deleteBanner(banner.id);
    setBanners((prev) => prev?.filter((b) => b.id !== banner.id) ?? null);
  }

  async function submitNew() {
    if (!form.title.trim() || !form.image_url.trim() || !form.action_value.trim()) return;
    setCreating(true);
    try {
      const created = await adminApi.createBanner({
        ...form,
        subtitle: form.subtitle || null,
        badge_text: form.badge_text || null,
      });
      setBanners((prev) => [...(prev ?? []), created]);
      setForm(EMPTY_FORM);
    } finally {
      setCreating(false);
    }
  }

  if (banners === null) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  return (
    <List>
      <Section header="Карусель на главной">
        {banners.map((b) => (
          <Cell
            key={b.id}
            multiline
            subtitle={`${b.action_type === "link" ? "ссылка" : "промпт"} · порядок ${b.sort_order}`}
            before={
              <img src={b.image_url} alt="" style={{ width: 48, height: 48, borderRadius: 8, objectFit: "cover" }} />
            }
            after={
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Switch checked={b.is_active} onChange={() => toggleActive(b)} />
                <Button size="s" mode="plain" onClick={() => remove(b)}>
                  🗑
                </Button>
              </div>
            }
          >
            {b.title}
          </Cell>
        ))}
      </Section>

      <Section header="Новый баннер">
        <Cell>
          <Input
            header="Заголовок"
            placeholder="Заголовок"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
        </Cell>
        <Cell>
          <Input
            header="Подзаголовок"
            placeholder="Подзаголовок"
            value={form.subtitle ?? ""}
            onChange={(e) => setForm({ ...form, subtitle: e.target.value })}
          />
        </Cell>
        <Cell>
          <Input
            header="Бейдж (напр. Новое)"
            placeholder="Бейдж (напр. Новое)"
            value={form.badge_text ?? ""}
            onChange={(e) => setForm({ ...form, badge_text: e.target.value })}
          />
        </Cell>
        <Cell>
          <Input
            header="Текст кнопки"
            placeholder="Текст кнопки"
            value={form.cta_text}
            onChange={(e) => setForm({ ...form, cta_text: e.target.value })}
          />
        </Cell>
        <Cell>
          <Input
            header="URL картинки"
            placeholder="https://..."
            value={form.image_url}
            onChange={(e) => setForm({ ...form, image_url: e.target.value })}
          />
        </Cell>
        <Cell>
          <Select
            header="Действие по клику"
            value={form.action_type}
            onChange={(e) => setForm({ ...form, action_type: e.target.value as "prompt" | "link" })}
          >
            <option value="prompt">Открыть чат с промптом</option>
            <option value="link">Открыть внешнюю ссылку</option>
          </Select>
        </Cell>
        <Cell>
          <Input
            header={form.action_type === "link" ? "URL ссылки" : "Текст промпта"}
            placeholder={form.action_type === "link" ? "https://..." : "Текст промпта"}
            value={form.action_value}
            onChange={(e) => setForm({ ...form, action_value: e.target.value })}
          />
        </Cell>
        <Cell>
          <Input
            type="number"
            header="Порядок сортировки"
            value={String(form.sort_order)}
            onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) || 0 })}
          />
        </Cell>
        <Cell>
          <Button stretched loading={creating} onClick={submitNew}>
            Добавить баннер
          </Button>
        </Cell>
      </Section>
    </List>
  );
}
