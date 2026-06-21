import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";

export function AppShell() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const isSystemAdmin = user?.roles.includes("system_admin") ?? false;
  const isShiftManager = user?.roles.includes("shift_manager") ?? false;
  const isSupervisor = user?.roles.includes("supervisor") ?? false;
  const canViewOperations = isSystemAdmin || isShiftManager || isSupervisor;
  const canManageAssignments = isSystemAdmin || isShiftManager;
  const isSelfOnly = user?.roles.includes("staff") || user?.roles.includes("viewer");

  const logout = async () => {
    await api("/api/v1/auth/logout/", { method: "POST", body: JSON.stringify({}) });
    setUser(null);
    navigate("/login");
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">Find Sports Club</p>
          <h1>FindManager</h1>
        </div>
        <nav className="side-nav">
          {(isSystemAdmin || isShiftManager || isSupervisor) && <NavLink to="/staff">スタッフ管理</NavLink>}
          {isSystemAdmin && (
            <>
              <NavLink to="/operations/locations">施設管理</NavLink>
              <NavLink to="/operations/work-areas">作業エリア</NavLink>
              <NavLink to="/operations/work-categories">作業カテゴリ</NavLink>
              <NavLink to="/operations/work-types">作業種別</NavLink>
            </>
          )}
          {canViewOperations && <NavLink to="/operations/work-type-availabilities">作業種別適用</NavLink>}
          {canManageAssignments && (
            <>
              <NavLink to="/operations/staff-locations">スタッフ所属</NavLink>
              <NavLink to="/operations/staff-capabilities">スタッフ対応可能業務</NavLink>
            </>
          )}
          {(isSelfOnly || canViewOperations) && (
            <>
              <NavLink to="/operations/my-staff-locations">自分の所属</NavLink>
              <NavLink to="/operations/my-capabilities">自分の対応可能業務</NavLink>
            </>
          )}
        </nav>
      </aside>
      <div className="content-area">
        <header className="header">
          <div>
            <strong>{user?.display_name}</strong>
            <div className="subtle-text">
              {user?.employee_code} / {user?.roles.join(", ")}
            </div>
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
