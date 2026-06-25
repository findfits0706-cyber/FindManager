import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";

type NavItem = {
  to: string;
  label: string;
};

export function AppShell() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const roles = user?.roles ?? [];
  const isSystemAdmin = roles.includes("system_admin");
  const isShiftManager = roles.includes("shift_manager");
  const isSupervisor = roles.includes("supervisor");
  const isStaff = roles.includes("staff");
  const isViewer = roles.includes("viewer");

  const canViewStaff = isSystemAdmin || isShiftManager || isSupervisor;
  const canViewOperations = isSystemAdmin || isShiftManager || isSupervisor;
  const canViewAssignments = isSystemAdmin || isShiftManager || isSupervisor;
  const canViewShiftSettings = isSystemAdmin || isShiftManager || isSupervisor;
  const canViewSelfPages = canViewOperations || isStaff || isViewer;

  const navItems: NavItem[] = [
    ...(canViewStaff ? [{ to: "/staff", label: "スタッフ管理" }] : []),
    ...(canViewOperations
      ? [
          { to: "/operations/locations", label: "拠点管理" },
          { to: "/operations/work-areas", label: "業務エリア" },
          { to: "/operations/work-categories", label: "業務カテゴリ" },
          { to: "/operations/work-types", label: "業務種別" },
          { to: "/operations/work-type-availabilities", label: "業務種別適用" },
        ]
      : []),
    ...(canViewAssignments
      ? [
          { to: "/operations/staff-locations", label: "スタッフ所属" },
          { to: "/operations/staff-capabilities", label: "スタッフ対応可能業務" },
        ]
      : []),
    ...(canViewShiftSettings
      ? [
          { to: "/shifts/monthly", label: "月間シフト" },
          { to: "/shifts/patterns", label: "勤務パターン" },
          { to: "/shifts/templates", label: "週間テンプレート" },
        ]
      : []),
    ...(canViewSelfPages
      ? [
          { to: "/operations/my-staff-locations", label: "自分の所属" },
          { to: "/operations/my-capabilities", label: "自分の対応可能業務" },
        ]
      : []),
  ];

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
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="content-area">
        <header className="header">
          <div>
            <strong>{user?.display_name}</strong>
            <div className="subtle-text">
              {user?.employee_code} / {roles.join(", ")}
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
