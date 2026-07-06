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
      className="brand-button press-scale"
      style={{
        position: "fixed",
        right: 16,
        bottom: 80,
        width: 58,
        height: 58,
        borderRadius: "50%",
        fontSize: 24,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 2,
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

      <div
        style={{
          position: "fixed",
          left: 0,
          right: 0,
          bottom: 0,
          zIndex: 2,
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          background: "rgba(10,10,12,0.72)",
          borderTop: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <Tabbar>
          {TABS.map((tab) => {
            const selected = location.pathname === tab.path;
            return (
              <Tabbar.Item key={tab.path} text={tab.text} selected={selected} onClick={() => navigate(tab.path)}>
                <span
                  style={{
                    fontSize: 20,
                    transition: "transform 200ms cubic-bezier(0.16,1,0.3,1)",
                    transform: selected ? "scale(1.12)" : "scale(1)",
                    filter: selected ? "drop-shadow(0 0 8px rgba(255,45,120,0.6))" : "none",
                    display: "inline-block",
                  }}
                >
                  {tab.icon}
                </span>
              </Tabbar.Item>
            );
          })}
        </Tabbar>
      </div>
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
