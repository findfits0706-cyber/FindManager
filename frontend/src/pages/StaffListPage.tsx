import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
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
    const error = query.error instanceof ApiError ? query.error : null;
    return (
      <section className="card staff-list-error" role="alert" aria-live="polite">
        <h2>スタッフ一覧を取得できませんでした。</h2>
        <p className="error">{error?.message ?? "予期しないエラーが発生しました。"}</p>
        {error && error.status > 0 ? <p>HTTPステータス: {error.status}</p> : null}
        {error?.requestId ? <p className="request-id">リクエストID: {error.requestId}</p> : null}
        <button type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>
          再読込
        </button>
      </section>
    );
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
