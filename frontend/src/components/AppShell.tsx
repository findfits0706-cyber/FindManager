import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";

const operationsLinks = [
  { to: "/operations/locations", label: "Locations" },
  { to: "/operations/work-areas", label: "Work Areas" },
  { to: "/operations/work-categories", label: "Work Categories" },
  { to: "/operations/work-types", label: "Work Types" },
  { to: "/operations/staff-locations", label: "Staff Locations" },
  { to: "/operations/staff-capabilities", label: "Staff Capabilities" },
  { to: "/operations/my-capabilities", label: "My Capabilities" },
];

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
        <div className="brand-block">
          <p className="eyebrow">Find Sports Club</p>
          <h1>FindManager</h1>
        </div>
        <nav className="side-nav">
          <NavLink to="/staff">Staff</NavLink>
          {operationsLinks.map((item) => (
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
              {user?.employee_code} · {user?.roles.join(", ")}
            </div>
          </div>
          <button type="button" onClick={() => void logout()}>
            Logout
          </button>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
