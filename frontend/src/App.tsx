import { AppRoot, Tabbar } from "@telegram-apps/telegram-ui";
import { HashRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { MeProvider } from "./context/MeContext";
import AdminPanel from "./screens/admin/AdminPanel";
import Chat from "./screens/Chat";
import Home from "./screens/Home";
import MyAccount from "./screens/MyAccount";
import Referral from "./screens/Referral";
import Settings from "./screens/Settings";
import Tariffs from "./screens/Tariffs";
import Trends from "./screens/Trends";

const TABS = [
  { path: "/", text: "Home", icon: "🏠" },
  { path: "/trends", text: "Trends", icon: "✨" },
  { path: "/account", text: "My Account", icon: "👤" },
];

function Fab() {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate("/chat")}
      aria-label="Открыть чат с нейросетью"
      style={{
        position: "fixed",
        right: 16,
        bottom: 76,
        width: 56,
        height: 56,
        borderRadius: "50%",
        border: "none",
        background: "linear-gradient(135deg, #ff5f6d, #ff2d78 55%, #b721ff)",
        boxShadow: "0 6px 20px rgba(255, 45, 120, 0.55)",
        color: "#fff",
        fontSize: 24,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
        cursor: "pointer",
      }}
    >
      ✨
    </button>
  );
}

function Shell() {
  const location = useLocation();
  const navigate = useNavigate();
  const showFab = !["/chat"].includes(location.pathname);

  return (
    <>
      <div style={{ paddingBottom: 64, minHeight: "100vh" }}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/account" element={<MyAccount />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/tariffs" element={<Tariffs />} />
          <Route path="/referral" element={<Referral />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/admin" element={<AdminPanel />} />
        </Routes>
      </div>

      {showFab && <Fab />}

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
