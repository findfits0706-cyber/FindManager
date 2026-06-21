import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Paginated, Staff } from "../lib/types";

export function StaffListPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const canManage = !!user?.permissions?.includes("accounts.manage_staff_basic");

  const query = useQuery({
    queryKey: ["staff"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/"),
  });

  const deactivate = async (staff: Staff) => {
    const confirmed = window.confirm(`Deactivate ${staff.display_name}?`);
    if (!confirmed) return;
    await api(`/api/v1/staff/${staff.id}/deactivate/`, {
      method: "POST",
      body: JSON.stringify({ reason: "Managed from staff list", employment_status: "suspended" }),
    });
    await query.refetch();
  };

  if (query.isLoading) {
    return <div>Loading staff...</div>;
  }

  if (query.isError) {
    return <div className="error">Failed to load staff.</div>;
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Accounts</p>
          <h2>Staff</h2>
        </div>
        {canManage ? (
          <button type="button" onClick={() => navigate("/staff/new")}>
            Add Staff
          </button>
        ) : null}
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Employee Code</th>
            <th>Username</th>
            <th>Status</th>
            <th>Roles</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {query.data?.results.map((staff) => (
            <tr key={staff.id}>
              <td>{staff.display_name}</td>
              <td>{staff.employee_code}</td>
              <td>{staff.username}</td>
              <td>{staff.employment_status}</td>
              <td>{staff.roles.join(", ")}</td>
              <td className="actions">
                <Link to={`/staff/${staff.id}`}>Open</Link>
                {canManage && staff.is_active ? (
                  <button type="button" onClick={() => void deactivate(staff)}>
                    Deactivate
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
