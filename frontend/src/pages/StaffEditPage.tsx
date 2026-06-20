import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Staff } from "../lib/types";

const roleOptions = ["system_admin", "shift_manager", "supervisor", "staff", "viewer"];

export function StaffEditPage({ mode }: { mode: "create" | "edit" }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const query = useQuery({
    enabled: mode === "edit" && !!id,
    queryKey: ["staff", id],
    queryFn: () => api<Staff>(`/api/v1/staff/${id}/`),
  });
  const staff = query.data;

  const [form, setForm] = useState({
    username: staff?.username ?? "",
    display_name: staff?.display_name ?? "",
    employee_code: staff?.employee_code ?? "",
    email: staff?.email ?? "",
    employment_status: staff?.employment_status ?? "active",
    hire_date: staff?.hire_date ?? "",
    termination_date: staff?.termination_date ?? "",
    roles: staff?.roles ?? ["staff"],
    temporary_password: "",
    must_change_password: true,
  });

  const onChange = (key: string, value: string | boolean | string[]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const payload = { ...form };
      const path = mode === "create" ? "/api/v1/staff/" : `/api/v1/staff/${id}/`;
      const method = mode === "create" ? "POST" : "PATCH";
      await api(path, { method, body: JSON.stringify(payload) });
      navigate("/staff");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "保存に失敗しました。");
    }
  };

  return (
    <section className="card">
      <h2>{mode === "create" ? "スタッフ新規作成" : "スタッフ編集"}</h2>
      <form className="form-grid" onSubmit={submit}>
        <label>
          氏名
          <input
            value={form.display_name}
            onChange={(e) => onChange("display_name", e.target.value)}
          />
        </label>
        <label>
          社員コード
          <input
            value={form.employee_code}
            onChange={(e) => onChange("employee_code", e.target.value)}
          />
        </label>
        <label>
          ユーザー名
          <input value={form.username} onChange={(e) => onChange("username", e.target.value)} />
        </label>
        <label>
          メール
          <input value={form.email} onChange={(e) => onChange("email", e.target.value)} />
        </label>
        <label>
          状態
          <select
            value={form.employment_status}
            onChange={(e) => onChange("employment_status", e.target.value)}
          >
            <option value="active">active</option>
            <option value="leave_of_absence">leave_of_absence</option>
            <option value="suspended">suspended</option>
            <option value="terminated">terminated</option>
          </select>
        </label>
        <label>
          入社日
          <input type="date" value={form.hire_date ?? ""} onChange={(e) => onChange("hire_date", e.target.value)} />
        </label>
        <label>
          退職日
          <input
            type="date"
            value={form.termination_date ?? ""}
            onChange={(e) => onChange("termination_date", e.target.value)}
          />
        </label>
        <label>
          一時パスワード
          <input
            type="password"
            value={form.temporary_password}
            onChange={(e) => onChange("temporary_password", e.target.value)}
          />
        </label>
        <fieldset>
          <legend>権限グループ</legend>
          {roleOptions.map((role) => (
            <label key={role} className="checkbox">
              <input
                type="checkbox"
                checked={form.roles.includes(role)}
                onChange={(e) =>
                  onChange(
                    "roles",
                    e.target.checked
                      ? [...form.roles, role]
                      : form.roles.filter((item) => item !== role),
                  )
                }
              />
              {role}
            </label>
          ))}
        </fieldset>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.must_change_password}
            onChange={(e) => onChange("must_change_password", e.target.checked)}
          />
          初回変更必須
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit">保存</button>
      </form>
    </section>
  );
}
