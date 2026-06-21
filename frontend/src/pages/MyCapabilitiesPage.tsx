import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { MyCapability, Paginated } from "../lib/types";

export function MyCapabilitiesPage() {
  const query = useQuery({
    queryKey: ["my-capabilities"],
    queryFn: () => api<Paginated<MyCapability>>("/api/v1/my-capabilities/?page_size=100"),
  });

  if (query.isLoading) {
    return <div>Loading capabilities...</div>;
  }

  if (query.isError) {
    return <div className="error">Failed to load capabilities.</div>;
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h2>My Capabilities</h2>
        </div>
      </div>
      <div className="capability-grid">
        {query.data?.results.map((capability) => (
          <article key={capability.id} className="capability-card">
            <strong>{capability.work_type_name}</strong>
            <span>{capability.location_name}</span>
            <span>Level: {capability.level}</span>
            <span>Valid From: {capability.valid_from}</span>
            <span>Approved By: {capability.approved_by_display_name || "-"}</span>
            <span>Status: {capability.is_active ? "active" : "inactive"}</span>
            {capability.notes ? <p>{capability.notes}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
