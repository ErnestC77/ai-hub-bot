"use client";

import { useState } from "react";

import { Placeholder } from "@/components/ui/placeholder";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useMe } from "@/context/MeContext";
import AdminBanners from "@/screens/admin/AdminBanners";
import AdminModelOptions from "@/screens/admin/AdminModelOptions";
import AdminModels from "@/screens/admin/AdminModels";
import AdminPackages from "@/screens/admin/AdminPackages";
import AdminPayments from "@/screens/admin/AdminPayments";
import AdminSettings from "@/screens/admin/AdminSettings";
import AdminSources from "@/screens/admin/AdminSources";
import AdminStats from "@/screens/admin/AdminStats";
import AdminUsers from "@/screens/admin/AdminUsers";

const TABS = [
  { key: "stats", label: "Статистика" },
  { key: "sources", label: "Источники" },
  { key: "users", label: "Пользователи" },
  { key: "payments", label: "Платежи" },
  { key: "models", label: "Модели" },
  { key: "options", label: "Опции" },
  { key: "packages", label: "Пакеты" },
  { key: "settings", label: "Настройки" },
  { key: "banners", label: "Карусель" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function AdminPanel() {
  const { me, loading } = useMe();
  const [tab, setTab] = useState<TabKey>("stats");

  if (loading) return null;
  if (!me?.is_admin) {
    return <Placeholder header="Доступ запрещён" description="Этот раздел только для администраторов." />;
  }

  return (
    <div>
      <div className="overflow-x-auto p-3">
        <SegmentedControl>
          {TABS.map((t) => (
            <SegmentedControl.Item key={t.key} selected={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </SegmentedControl.Item>
          ))}
        </SegmentedControl>
      </div>

      {tab === "stats" && <AdminStats />}
      {tab === "sources" && <AdminSources />}
      {tab === "users" && <AdminUsers />}
      {tab === "payments" && <AdminPayments />}
      {tab === "models" && <AdminModels />}
      {tab === "options" && <AdminModelOptions />}
      {tab === "packages" && <AdminPackages />}
      {tab === "settings" && <AdminSettings />}
      {tab === "banners" && <AdminBanners />}
    </div>
  );
}
