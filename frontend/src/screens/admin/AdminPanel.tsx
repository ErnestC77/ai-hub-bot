import { useState } from "react";
import { Placeholder, SegmentedControl } from "@telegram-apps/telegram-ui";

import { useMe } from "../../context/MeContext";
import AdminModels from "./AdminModels";
import AdminPayments from "./AdminPayments";
import AdminStats from "./AdminStats";
import AdminTariffs from "./AdminTariffs";
import AdminUsers from "./AdminUsers";

const TABS = [
  { key: "stats", label: "Статистика" },
  { key: "users", label: "Пользователи" },
  { key: "payments", label: "Платежи" },
  { key: "models", label: "Модели" },
  { key: "tariffs", label: "Тарифы" },
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
      <div style={{ padding: 12, overflowX: "auto" }}>
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
    </div>
  );
}
