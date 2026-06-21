import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { MyCapability, MyStaffLocation, Paginated } from "../lib/types";

export function MyCapabilitiesPage({ section = "both" }: { section?: "both" | "locations" | "capabilities" }) {
  const locationsQuery = useQuery({
    enabled: section === "both" || section === "locations",
    queryKey: ["my-staff-locations"],
    queryFn: () => api<Paginated<MyStaffLocation>>("/api/v1/my-staff-locations/?page_size=100"),
  });
  const capabilitiesQuery = useQuery({
    enabled: section === "both" || section === "capabilities",
    queryKey: ["my-capabilities"],
    queryFn: () => api<Paginated<MyCapability>>("/api/v1/my-capabilities/?page_size=100"),
  });

  if (locationsQuery.isLoading || capabilitiesQuery.isLoading) {
    return <div>読み込み中...</div>;
  }

  if (locationsQuery.isError || capabilitiesQuery.isError) {
    return <div className="error">自分の情報の取得に失敗しました。</div>;
  }

  return (
    <section className="card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Operations</p>
          <h2>自分の所属・対応可能業務</h2>
        </div>
      </div>
      {(section === "both" || section === "locations") && (
        <>
          <h3>所属情報</h3>
          <table className="table">
            <thead>
              <tr>
                <th>施設名</th>
                <th>主所属</th>
                <th>有効開始日</th>
                <th>有効終了日</th>
                <th>状態</th>
              </tr>
            </thead>
            <tbody>
              {locationsQuery.data?.results.map((location) => (
                <tr key={location.id}>
                  <td>{location.location_name}</td>
                  <td>{location.is_primary ? "主所属" : "-"}</td>
                  <td>{location.valid_from}</td>
                  <td>{location.valid_until ?? "-"}</td>
                  <td>{location.is_active ? "有効" : "無効"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {(section === "both" || section === "capabilities") && (
        <>
          <h3>対応可能業務</h3>
          <table className="table">
            <thead>
              <tr>
                <th>業務名</th>
                <th>レベル</th>
                <th>施設名</th>
                <th>有効開始日</th>
                <th>承認者</th>
                <th>承認日時</th>
                <th>状態</th>
              </tr>
            </thead>
            <tbody>
              {capabilitiesQuery.data?.results.map((capability) => (
                <tr key={capability.id}>
                  <td>{capability.work_type_name}</td>
                  <td>{capability.level}</td>
                  <td>{capability.location_name ?? "-"}</td>
                  <td>{capability.valid_from}</td>
                  <td>{capability.approved_by_display_name || "-"}</td>
                  <td>{capability.approved_at ?? "-"}</td>
                  <td>{capability.is_active ? "有効" : "無効"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
