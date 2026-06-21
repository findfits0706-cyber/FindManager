import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type { Location, Paginated, WorkCategory } from "../lib/types";

type ResourceKey = "locations" | "work-areas" | "work-categories" | "work-types";
type FormField = {
  name: string;
  label: string;
  type: "text" | "number" | "checkbox" | "select";
  options?: Array<{ value: string; label: string }>;
};

const colorOptions = ["slate", "blue", "green", "amber", "red", "violet", "cyan", "pink"].map((value) => ({
  value,
  label: value,
}));

function toInitialValues(fields: FormField[]) {
  return Object.fromEntries(fields.map((field) => [field.name, field.type === "checkbox" ? false : ""]));
}

export function OperationsMasterPage({ resource }: { resource: ResourceKey }) {
  const { user } = useAuth();
  const canManage = user?.roles.includes("system_admin") ?? false;
  const [error, setError] = useState("");

  const locationQuery = useQuery({
    queryKey: ["locations", "options"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
  });
  const categoryQuery = useQuery({
    queryKey: ["work-categories", "options"],
    queryFn: () => api<Paginated<WorkCategory>>("/api/v1/work-categories/?page_size=100"),
  });

  const config = useMemo(() => {
    const locationOptions = (locationQuery.data?.results ?? []).map((item) => ({ value: item.id, label: item.name }));
    const categoryOptions = (categoryQuery.data?.results ?? []).map((item) => ({ value: item.id, label: item.name }));
    const base = {
      locations: {
        title: "Locations",
        endpoint: "/api/v1/locations/",
        fields: [
          { name: "code", label: "Code", type: "text" },
          { name: "name", label: "Name", type: "text" },
          { name: "short_name", label: "Short Name", type: "text" },
          { name: "timezone", label: "Timezone", type: "text" },
        ] satisfies FormField[],
      },
      "work-areas": {
        title: "Work Areas",
        endpoint: "/api/v1/work-areas/",
        fields: [
          { name: "location", label: "Location", type: "select", options: locationOptions },
          { name: "code", label: "Code", type: "text" },
          { name: "name", label: "Name", type: "text" },
        ] satisfies FormField[],
      },
      "work-categories": {
        title: "Work Categories",
        endpoint: "/api/v1/work-categories/",
        fields: [
          { name: "code", label: "Code", type: "text" },
          { name: "name", label: "Name", type: "text" },
        ] satisfies FormField[],
      },
      "work-types": {
        title: "Work Types",
        endpoint: "/api/v1/work-types/",
        fields: [
          { name: "category", label: "Category", type: "select", options: categoryOptions },
          { name: "code", label: "Code", type: "text" },
          { name: "name", label: "Name", type: "text" },
          { name: "short_name", label: "Short Name", type: "text" },
          { name: "default_duration_minutes", label: "Default Minutes", type: "number" },
          { name: "minimum_staff_count", label: "Min Staff", type: "number" },
          { name: "color_key", label: "Color", type: "select", options: colorOptions },
          { name: "requires_capability", label: "Requires Capability", type: "checkbox" },
          { name: "can_overlap", label: "Can Overlap", type: "checkbox" },
          { name: "is_break", label: "Break", type: "checkbox" },
          { name: "is_bookable", label: "Bookable", type: "checkbox" },
          { name: "requires_customer", label: "Requires Customer", type: "checkbox" },
        ] satisfies FormField[],
      },
    } as const;
    return base[resource];
  }, [categoryQuery.data?.results, locationQuery.data?.results, resource]);

  const [form, setForm] = useState<Record<string, string | boolean>>(() => toInitialValues(config.fields));
  const listQuery = useQuery({
    queryKey: [resource],
    queryFn: () => api<Paginated<Record<string, unknown>>>(`${config.endpoint}?page_size=100`),
  });

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const payload = Object.fromEntries(
        config.fields
          .map((field) => {
            const rawValue = form[field.name];
            if (field.type === "checkbox") return [field.name, rawValue];
            if (field.type === "number") return [field.name, Number(rawValue || 0)];
            return [field.name, rawValue];
          })
          .filter(([, value]) => value !== ""),
      );
      await api(config.endpoint, { method: "POST", body: JSON.stringify(payload) });
      setForm(toInitialValues(config.fields));
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
    return <div>Loading {config.title.toLowerCase()}...</div>;
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
          <div className="field-grid">
            {config.fields.map((field) => (
              <label key={field.name}>
                {field.label}
                {field.type === "select" ? (
                  <select
                    value={String(form[field.name] ?? "")}
                    onChange={(e) => setForm((current) => ({ ...current, [field.name]: e.target.value }))}
                  >
                    <option value="">Select</option>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : field.type === "checkbox" ? (
                  <input
                    type="checkbox"
                    checked={Boolean(form[field.name])}
                    onChange={(e) => setForm((current) => ({ ...current, [field.name]: e.target.checked }))}
                  />
                ) : (
                  <input
                    type={field.type}
                    value={String(form[field.name] ?? "")}
                    onChange={(e) => setForm((current) => ({ ...current, [field.name]: e.target.value }))}
                  />
                )}
              </label>
            ))}
          </div>
          {error ? <p className="error">{error}</p> : null}
          <div className="actions">
            <button type="submit">Add {config.title.slice(0, -1)}</button>
          </div>
        </form>
      ) : null}
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Code</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {listQuery.data?.results.map((item) => (
            <tr key={String(item.id)}>
              <td>{String(item.name ?? item.short_name ?? item.id)}</td>
              <td>{String(item.code ?? "-")}</td>
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
