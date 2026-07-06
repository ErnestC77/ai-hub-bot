import { useState } from "react";
import { Button, Cell, IconButton, List, Placeholder, Progress, Section, Spinner } from "@telegram-apps/telegram-ui";
import { useNavigate } from "react-router-dom";

import { useMe } from "../context/MeContext";
import CreditPurchaseSheet from "./account/CreditPurchaseSheet";

const CATEGORY_LABEL: Record<string, string> = {
  fast: "Быстрые запросы",
  medium: "Средние запросы",
  premium: "Премиум запросы",
  image: "Картинки",
};

export default function MyAccount() {
  const { me, loading } = useMe();
  const navigate = useNavigate();
  const [buyingCredits, setBuyingCredits] = useState(false);

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (!me) {
    return <Placeholder header="Не удалось загрузить профиль" description="Откройте приложение из Telegram." />;
  }

  const categories = Object.entries(me.limits.categories).filter(([, v]) => v.limit > 0);
  const isFree = me.tariff_code === "free";

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ margin: "8px 0 16px", textAlign: "center" }}>
        @{me.username ?? me.first_name ?? me.telegram_id}
      </h2>

      <div style={{ borderRadius: 16, background: "var(--tgui--secondary_bg_color)", padding: 16, marginBottom: 16 }}>
        <div style={{ fontSize: 12, opacity: 0.6, textTransform: "uppercase" }}>Current plan</div>
        <div style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 12px" }}>{me.tariff_name}</div>

        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
          <span style={{ opacity: 0.7 }}>Дневные запросы</span>
          <span>
            {me.limits.daily_used} / {me.limits.daily_limit}
          </span>
        </div>
        <Progress
          value={me.limits.daily_limit > 0 ? Math.min(100, (me.limits.daily_used / me.limits.daily_limit) * 100) : 0}
        />

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 12 }}>
          {categories.map(([category, limit]) => (
            <span
              key={category}
              style={{
                fontSize: 12,
                padding: "4px 10px",
                borderRadius: 999,
                background: "rgba(255,255,255,0.08)",
              }}
            >
              {CATEGORY_LABEL[category] ?? category}: {limit.limit - limit.used}/{limit.limit}
            </span>
          ))}
          {me.subscription_expires_at && (
            <span style={{ fontSize: 12, opacity: 0.6 }}>
              до {new Date(me.subscription_expires_at).toLocaleDateString("ru-RU")}
            </span>
          )}
        </div>
      </div>

      {isFree && (
        <div
          style={{
            borderRadius: 16,
            padding: 16,
            marginBottom: 16,
            background: "linear-gradient(135deg, #ff5f6d, #b721ff)",
          }}
        >
          <div style={{ fontSize: 18, fontWeight: 700 }}>🚀 Go Premium</div>
          <div style={{ fontSize: 13, opacity: 0.9, margin: "4px 0 12px" }}>
            Больше запросов, доступ к premium-моделям и генерации картинок
          </div>
          <Button stretched mode="white" onClick={() => navigate("/tariffs")}>
            Unlock Premium
          </Button>
        </div>
      )}

      <div style={{ fontSize: 12, opacity: 0.6, textTransform: "uppercase", margin: "8px 0" }}>Credits</div>
      <List>
        <Section>
          <Cell
            subtitle="Тратятся, когда лимит тарифа исчерпан"
            after={
              <IconButton onClick={() => setBuyingCredits(true)} aria-label="Купить кредиты">
                +
              </IconButton>
            }
          >
            💎 {me.credits_balance} кредитов
          </Cell>
        </Section>

        <Section header="Settings">
          <Cell onClick={() => navigate("/settings")}>⚙️ Настройки и поддержка</Cell>
          <Cell onClick={() => navigate("/referral")}>🎁 Реферальная программа</Cell>
          {me.is_admin && <Cell onClick={() => navigate("/admin")}>🛠 Админ-панель</Cell>}
        </Section>
      </List>

      {buyingCredits && <CreditPurchaseSheet onClose={() => setBuyingCredits(false)} />}
    </div>
  );
}
