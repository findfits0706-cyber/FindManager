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
    const confirmed = window.confirm(`${staff.display_name} を利用停止しますか？`);
    if (!confirmed) return;
    await api(`/api/v1/staff/${staff.id}/deactivate/`, {
      method: "POST",
      body: JSON.stringify({ reason: "画面から実行", employment_status: "suspended" }),
    });
    await query.refetch();
  };

  if (query.isLoading) {
    return <div>読み込み中...</div>;
  }

  if (query.isError) {
    return <div className="error">一覧の取得に失敗しました。</div>;
  }

  return (
    <section className="card">
      <div className="section-header">
        <h2>スタッフ一覧</h2>
        {canManage ? (
          <button type="button" onClick={() => navigate("/staff/new")}>
            新規作成
          </button>
        ) : null}
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>氏名</th>
            <th>社員コード</th>
            <th>ユーザー名</th>
            <th>状態</th>
            <th>権限</th>
            <th>操作</th>
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
                <Link to={`/staff/${staff.id}`}>詳細</Link>
                {canManage && staff.is_active ? (
                  <button type="button" onClick={() => void deactivate(staff)}>
                    利用停止
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
