import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Location, Paginated, Staff, WorkType } from "../lib/types";

type ResourceKey = "staff-locations" | "staff-capabilities";

export function StaffAssignmentsPage({ resource }: { resource: ResourceKey }) {
  const { user } = useAuth();
  const canManage = user?.roles.includes("system_admin") || user?.roles.includes("shift_manager");
  const [error, setError] = useState("");

  const staffQuery = useQuery({
    enabled: !!canManage,
    queryKey: ["staff", "options"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=100"),
  });
  const locationQuery = useQuery({
    queryKey: ["locations", "options"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
  });
  const workTypeQuery = useQuery({
    enabled: resource === "staff-capabilities",
    queryKey: ["work-types", "options"],
    queryFn: () => api<Paginated<WorkType>>("/api/v1/work-types/?page_size=100"),
  });

  const config = useMemo(() => {
    const staffOptions = (staffQuery.data?.results ?? []).map((item) => ({ value: item.id, label: item.display_name }));
    const locationOptions = (locationQuery.data?.results ?? []).map((item) => ({ value: item.id, label: item.name }));
    const workTypeOptions = (workTypeQuery.data?.results ?? []).map((item) => ({ value: item.id, label: item.name }));
    return resource === "staff-locations"
      ? {
          title: "Staff Locations",
          endpoint: "/api/v1/staff-locations/",
          initial: { staff: "", location: "", is_primary: false, valid_from: "" } as Record<string, string | boolean>,
          renderForm: (form: Record<string, string | boolean>, setForm: React.Dispatch<React.SetStateAction<Record<string, string | boolean>>>) => (
            <div className="field-grid">
              <label>
                Staff
                <select value={String(form.staff)} onChange={(e) => setForm((current) => ({ ...current, staff: e.target.value }))}>
                  <option value="">Select</option>
                  {staffOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Location
                <select value={String(form.location)} onChange={(e) => setForm((current) => ({ ...current, location: e.target.value }))}>
                  <option value="">Select</option>
                  {locationOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Valid From
                <input type="date" value={String(form.valid_from)} onChange={(e) => setForm((current) => ({ ...current, valid_from: e.target.value }))} />
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={Boolean(form.is_primary)}
                  onChange={(e) => setForm((current) => ({ ...current, is_primary: e.target.checked }))}
                />
                Primary assignment
              </label>
            </div>
          ),
        }
      : {
          title: "Staff Capabilities",
          endpoint: "/api/v1/staff-capabilities/",
          initial: {
            staff: "",
            work_type: "",
            location: "",
            level: "trainee",
            valid_from: "",
            approved_by: "",
            notes: "",
          } as Record<string, string | boolean>,
          renderForm: (form: Record<string, string | boolean>, setForm: React.Dispatch<React.SetStateAction<Record<string, string | boolean>>>) => (
            <div className="field-grid">
              <label>
                Staff
                <select value={String(form.staff)} onChange={(e) => setForm((current) => ({ ...current, staff: e.target.value }))}>
                  <option value="">Select</option>
                  {staffOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Work Type
                <select value={String(form.work_type)} onChange={(e) => setForm((current) => ({ ...current, work_type: e.target.value }))}>
                  <option value="">Select</option>
                  {workTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Location
                <select value={String(form.location)} onChange={(e) => setForm((current) => ({ ...current, location: e.target.value }))}>
                  <option value="">Select</option>
                  {locationOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Level
                <select value={String(form.level)} onChange={(e) => setForm((current) => ({ ...current, level: e.target.value }))}>
                  <option value="trainee">trainee</option>
                  <option value="assisted">assisted</option>
                  <option value="independent">independent</option>
                  <option value="trainer">trainer</option>
                </select>
              </label>
              <label>
                Valid From
                <input type="date" value={String(form.valid_from)} onChange={(e) => setForm((current) => ({ ...current, valid_from: e.target.value }))} />
              </label>
              <label>
                Approved By
                <select value={String(form.approved_by)} onChange={(e) => setForm((current) => ({ ...current, approved_by: e.target.value }))}>
                  <option value="">Select</option>
                  {staffOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="full-width">
                Notes
                <input value={String(form.notes)} onChange={(e) => setForm((current) => ({ ...current, notes: e.target.value }))} />
              </label>
            </div>
          ),
        };
  }, [locationQuery.data?.results, resource, staffQuery.data?.results, workTypeQuery.data?.results]);

  const [form, setForm] = useState<Record<string, string | boolean>>(config.initial);
  const listQuery = useQuery({
    queryKey: [resource],
    queryFn: () => api<Paginated<Record<string, unknown>>>(`${config.endpoint}?page_size=100`),
  });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== ""));
      await api(config.endpoint, { method: "POST", body: JSON.stringify(payload) });
      setForm(config.initial);
      await listQuery.refetch();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Save failed.");
    }
  };

  const deactivate = async (itemId: string) => {
    await api(`${config.endpoint}${itemId}/deactivate/`, { method: "POST", body: JSON.stringify({ confirm: true }) });
    await listQuery.refetch();
  };

  if (listQuery.isLoading) {
    return <div>Loading...</div>;
  }

  if (listQuery.isError) {
    return <div className="error">Failed to load {config.title.toLowerCase()}.</div>;
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h2>{config.title}</h2>
        </div>
      </div>
      {canManage ? (
        <form className="form-grid compact-form" onSubmit={submit}>
          {config.renderForm(form, setForm)}
          {error ? <p className="error">{error}</p> : null}
          <div className="actions">
            <button type="submit">Add Record</button>
          </div>
        </form>
      ) : null}
      <table className="table">
        <thead>
          <tr>
            <th>Staff</th>
            <th>{resource === "staff-locations" ? "Location" : "Work Type"}</th>
            <th>{resource === "staff-locations" ? "Primary" : "Level"}</th>
            <th>Valid From</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {listQuery.data?.results.map((item) => (
            <tr key={String(item.id)}>
              <td>{String(item.staff_display_name ?? item.staff ?? "-")}</td>
              <td>{String(item.location_name ?? item.work_type_name ?? item.work_type ?? "-")}</td>
              <td>{String(item.is_primary ?? item.level ?? "-")}</td>
              <td>{String(item.valid_from ?? "-")}</td>
              <td>{item.is_active ? "active" : "inactive"}</td>
              <td className="actions">
                {canManage && item.is_active ? (
                  <button type="button" onClick={() => void deactivate(String(item.id))}>
                    Deactivate
                  </button>
                ) : (
                  <span className="subtle-text">Read only</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
