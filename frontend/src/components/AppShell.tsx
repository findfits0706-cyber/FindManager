import { Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";

export function AppShell() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const logout = async () => {
    await api("/api/v1/auth/logout/", { method: "POST", body: JSON.stringify({}) });
    setUser(null);
    navigate("/login");
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>FindManager</h1>
        <nav>
          <a href="/staff">スタッフ管理</a>
        </nav>
      </aside>
      <div className="content-area">
        <header className="header">
          <div>
            <strong>{user?.display_name}</strong>
            <div>{user?.roles.join(", ")}</div>
          </div>
          <button type="button" onClick={() => void logout()}>
            ログアウト
          </button>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
