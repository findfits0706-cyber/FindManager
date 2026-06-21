import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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
    username: "",
    display_name: "",
    employee_code: "",
    email: "",
    employment_status: "active",
    hire_date: "",
    termination_date: "",
    roles: ["staff"],
    temporary_password: "",
    must_change_password: true,
  });

  useEffect(() => {
    if (!staff) return;
    setForm({
      username: staff.username ?? "",
      display_name: staff.display_name ?? "",
      employee_code: staff.employee_code ?? "",
      email: staff.email ?? "",
      employment_status: staff.employment_status ?? "active",
      hire_date: staff.hire_date ?? "",
      termination_date: staff.termination_date ?? "",
      roles: staff.roles ?? ["staff"],
      temporary_password: "",
      must_change_password: staff.must_change_password,
    });
  }, [staff]);

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
      setError(submitError instanceof Error ? submitError.message : "Save failed.");
    }
  };

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Accounts</p>
          <h2>{mode === "create" ? "Create Staff" : "Edit Staff"}</h2>
        </div>
      </div>
      <form className="form-grid" onSubmit={submit}>
        <label>
          Display name
          <input value={form.display_name} onChange={(e) => onChange("display_name", e.target.value)} />
        </label>
        <label>
          Employee code
          <input value={form.employee_code} onChange={(e) => onChange("employee_code", e.target.value)} />
        </label>
        <label>
          Username
          <input value={form.username} onChange={(e) => onChange("username", e.target.value)} />
        </label>
        <label>
          Email
          <input value={form.email} onChange={(e) => onChange("email", e.target.value)} />
        </label>
        <label>
          Employment status
          <select value={form.employment_status} onChange={(e) => onChange("employment_status", e.target.value)}>
            <option value="active">active</option>
            <option value="leave_of_absence">leave_of_absence</option>
            <option value="suspended">suspended</option>
            <option value="terminated">terminated</option>
          </select>
        </label>
        <label>
          Hire date
          <input type="date" value={form.hire_date} onChange={(e) => onChange("hire_date", e.target.value)} />
        </label>
        <label>
          Termination date
          <input
            type="date"
            value={form.termination_date}
            onChange={(e) => onChange("termination_date", e.target.value)}
          />
        </label>
        <label>
          Temporary password
          <input
            type="password"
            value={form.temporary_password}
            onChange={(e) => onChange("temporary_password", e.target.value)}
          />
        </label>
        <fieldset>
          <legend>Roles</legend>
          <div className="checkbox-list">
            {roleOptions.map((role) => (
              <label key={role} className="checkbox">
                <input
                  type="checkbox"
                  checked={form.roles.includes(role)}
                  onChange={(e) =>
                    onChange(
                      "roles",
                      e.target.checked ? [...form.roles, role] : form.roles.filter((item) => item !== role),
                    )
                  }
                />
                {role}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.must_change_password}
            onChange={(e) => onChange("must_change_password", e.target.checked)}
          />
          Require password change on next login
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit">Save</button>
      </form>
    </section>
  );
}
