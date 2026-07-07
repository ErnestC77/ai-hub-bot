"use client";

import { useState } from "react";

import { Placeholder } from "@/components/ui/placeholder";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useMe } from "@/context/MeContext";
import AdminBanners from "@/screens/admin/AdminBanners";
import AdminModels from "@/screens/admin/AdminModels";
import AdminPayments from "@/screens/admin/AdminPayments";
import AdminStats from "@/screens/admin/AdminStats";
import AdminTariffs from "@/screens/admin/AdminTariffs";
import AdminUsers from "@/screens/admin/AdminUsers";

const TABS = [
  { key: "stats", label: "Статистика" },
  { key: "users", label: "Пользователи" },
  { key: "payments", label: "Платежи" },
  { key: "models", label: "Модели" },
  { key: "tariffs", label: "Тарифы" },
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
      {tab === "users" && <AdminUsers />}
      {tab === "payments" && <AdminPayments />}
      {tab === "models" && <AdminModels />}
      {tab === "tariffs" && <AdminTariffs />}
      {tab === "banners" && <AdminBanners />}
    </div>
  );
}
