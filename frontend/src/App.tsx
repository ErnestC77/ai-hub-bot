import { AppRoot, Tabbar } from "@telegram-apps/telegram-ui";
import { HashRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { MeProvider } from "./context/MeContext";
import AdminPanel from "./screens/admin/AdminPanel";
import Balance from "./screens/Balance";
import Chat from "./screens/Chat";
import Home from "./screens/Home";
import Referral from "./screens/Referral";
import Settings from "./screens/Settings";
import Tariffs from "./screens/Tariffs";
import Tools from "./screens/Tools";

const TABS = [
  { path: "/", text: "Главная", icon: "🏠" },
  { path: "/chat", text: "Чат", icon: "💬" },
  { path: "/tariffs", text: "Тарифы", icon: "💳" },
  { path: "/balance", text: "Баланс", icon: "📊" },
];

function Shell() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <>
      <div style={{ paddingBottom: 64, minHeight: "100vh" }}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/tools" element={<Tools />} />
          <Route path="/tariffs" element={<Tariffs />} />
          <Route path="/balance" element={<Balance />} />
          <Route path="/referral" element={<Referral />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/admin" element={<AdminPanel />} />
        </Routes>
      </div>

      <Tabbar>
        {TABS.map((tab) => (
          <Tabbar.Item
            key={tab.path}
            text={tab.text}
            selected={location.pathname === tab.path}
            onClick={() => navigate(tab.path)}
          >
            <span style={{ fontSize: 20 }}>{tab.icon}</span>
          </Tabbar.Item>
        ))}
      </Tabbar>
    </>
  );
}

export default function App() {
  return (
    <AppRoot appearance="dark">
      <MeProvider>
        <HashRouter>
          <Shell />
        </HashRouter>
      </MeProvider>
    </AppRoot>
  );
}
