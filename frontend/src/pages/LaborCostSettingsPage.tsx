import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import type {
  LaborCostAllowanceType,
  LaborCostEmploymentType,
  Location,
  Paginated,
  Staff,
  StaffAllowanceAssignment,
  StaffCompensationProfile,
} from "../lib/types";

type Resource = "rates" | "allowances";
type RateForm = {
  location: string;
  staff: string;
  employment_type: LaborCostEmploymentType;
  base_hourly_rate: string;
  fixed_monthly_amount: string;
  valid_from: string;
  valid_to: string;
  notes: string;
};
type AllowanceForm = {
  location: string;
  staff: string;
  code: string;
  name: string;
  allowance_type: LaborCostAllowanceType;
  amount: string;
  valid_from: string;
  valid_to: string;
  notes: string;
};

const initialRateForm: RateForm = {
  location: "",
  staff: "",
  employment_type: "hourly",
  base_hourly_rate: "",
  fixed_monthly_amount: "",
  valid_from: "",
  valid_to: "",
  notes: "",
};

const initialAllowanceForm: AllowanceForm = {
  location: "",
  staff: "",
  code: "",
  name: "",
  allowance_type: "per_worked_day",
  amount: "",
  valid_from: "",
  valid_to: "",
  notes: "",
};

function employmentTypeLabel(value: string) {
  const labels: Record<string, string> = { hourly: "時給", monthly_fixed: "月額固定", other: "その他" };
  return labels[value] ?? value;
}

function allowanceTypeLabel(value: string) {
  const labels: Record<string, string> = {
    per_worked_day: "勤務日数連動",
    per_worked_hour: "勤務時間連動",
    fixed_monthly: "月額固定",
    manual: "手入力",
  };
  return labels[value] ?? value;
}

export function LaborCostSettingsPage({ resource }: { resource: Resource }) {
  const { user, loading } = useAuth();
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const isRates = resource === "rates";
  const title = isRates ? "勤務単価設定" : "手当設定";
  const endpoint = isRates ? "/api/v1/staff-compensation-profiles/" : "/api/v1/staff-allowance-assignments/";
  const [location, setLocation] = useState("");
  const [staff, setStaff] = useState("");
  const [kind, setKind] = useState("");
  const [validOn, setValidOn] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [rateForm, setRateForm] = useState<RateForm>(initialRateForm);
  const [allowanceForm, setAllowanceForm] = useState<AllowanceForm>(initialAllowanceForm);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ page_size: "100", is_active: "true" });
    if (location) params.set("location", location);
    if (staff) params.set("staff", staff);
    if (validOn) params.set("valid_on", validOn);
    if (kind) params.set(isRates ? "employment_type" : "allowance_type", kind);
    return params.toString();
  }, [isRates, kind, location, staff, validOn]);

  const locationsQuery = useQuery({
    queryKey: ["labor-cost-locations"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100"),
    enabled: canManage,
  });
  const staffQuery = useQuery({
    queryKey: ["labor-cost-staff"],
    queryFn: () => api<Paginated<Staff>>("/api/v1/staff/?page_size=200"),
    enabled: canManage,
  });
  const listQuery = useQuery<Paginated<StaffCompensationProfile | StaffAllowanceAssignment>>({
    queryKey: [endpoint, queryString],
    queryFn: () => api<Paginated<StaffCompensationProfile | StaffAllowanceAssignment>>(`${endpoint}?${queryString}`),
    enabled: canManage,
  });

  useEffect(() => {
    setEditingId(null);
    setMessage("");
    setError("");
    setRateForm(initialRateForm);
    setAllowanceForm(initialAllowanceForm);
  }, [resource]);

  if (!loading && !canManage) return <Navigate to="/403" replace />;

  const resetForm = () => {
    setEditingId(null);
    setRateForm(initialRateForm);
    setAllowanceForm(initialAllowanceForm);
    setError("");
  };

  const editRate = (item: StaffCompensationProfile) => {
    setEditingId(item.id);
    setRateForm({
      location: item.location,
      staff: item.staff,
      employment_type: item.employment_type,
      base_hourly_rate: item.base_hourly_rate ?? "",
      fixed_monthly_amount: item.fixed_monthly_amount ?? "",
      valid_from: item.valid_from,
      valid_to: item.valid_to ?? "",
      notes: item.notes,
    });
  };

  const editAllowance = (item: StaffAllowanceAssignment) => {
    setEditingId(item.id);
    setAllowanceForm({
      location: item.location,
      staff: item.staff,
      code: item.code,
      name: item.name,
      allowance_type: item.allowance_type,
      amount: item.amount,
      valid_from: item.valid_from,
      valid_to: item.valid_to ?? "",
      notes: item.notes,
    });
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError("");
    setMessage("");
    const form = isRates ? rateForm : allowanceForm;
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== ""));
      await api(editingId ? `${endpoint}${editingId}/` : endpoint, {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      setMessage(editingId ? "更新しました。" : "作成しました。");
      resetForm();
      await listQuery.refetch();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const setActive = async (id: string, isActive: boolean) => {
    setIsSubmitting(true);
    setError("");
    setMessage("");
    try {
      await api(`${endpoint}${id}/`, { method: "PATCH", body: JSON.stringify({ is_active: isActive }) });
      setMessage(isActive ? "再有効化しました。" : "無効化しました。");
      await listQuery.refetch();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "状態変更に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const rates = isRates ? ((listQuery.data?.results ?? []) as StaffCompensationProfile[]) : [];
  const allowances = !isRates ? ((listQuery.data?.results ?? []) as StaffAllowanceAssignment[]) : [];

  return (
    <section className="card labor-page">
      <div className="section-header">
        <div>
          <p className="eyebrow">Labor cost estimate</p>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="toolbar field-grid">
        <label>
          拠点
          <select value={location} onChange={(event) => setLocation(event.target.value)}>
            <option value="">すべて</option>
            {locationsQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          スタッフ
          <select value={staff} onChange={(event) => setStaff(event.target.value)}>
            <option value="">すべて</option>
            {staffQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.employee_code} {item.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          種別
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="">すべて</option>
            {isRates ? (
              <>
                <option value="hourly">時給</option>
                <option value="monthly_fixed">月額固定</option>
                <option value="other">その他</option>
              </>
            ) : (
              <>
                <option value="per_worked_day">勤務日数連動</option>
                <option value="per_worked_hour">勤務時間連動</option>
                <option value="fixed_monthly">月額固定</option>
                <option value="manual">手入力</option>
              </>
            )}
          </select>
        </label>
        <label>
          有効日
          <input type="date" value={validOn} onChange={(event) => setValidOn(event.target.value)} />
        </label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      <form className="compact-form field-grid" onSubmit={(event) => void submit(event)}>
        <label>
          拠点
          <select
            value={isRates ? rateForm.location : allowanceForm.location}
            onChange={(event) =>
              isRates
                ? setRateForm((current) => ({ ...current, location: event.target.value }))
                : setAllowanceForm((current) => ({ ...current, location: event.target.value }))
            }
          >
            <option value="">選択</option>
            {locationsQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          スタッフ
          <select
            value={isRates ? rateForm.staff : allowanceForm.staff}
            onChange={(event) =>
              isRates
                ? setRateForm((current) => ({ ...current, staff: event.target.value }))
                : setAllowanceForm((current) => ({ ...current, staff: event.target.value }))
            }
          >
            <option value="">選択</option>
            {staffQuery.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.employee_code} {item.display_name}
              </option>
            ))}
          </select>
        </label>
        {isRates ? (
          <>
            <label>
              雇用区分
              <select
                value={rateForm.employment_type}
                onChange={(event) =>
                  setRateForm((current) => ({
                    ...current,
                    employment_type: event.target.value as LaborCostEmploymentType,
                  }))
                }
              >
                <option value="hourly">時給</option>
                <option value="monthly_fixed">月額固定</option>
                <option value="other">その他</option>
              </select>
            </label>
            <label>
              時給
              <input
                inputMode="decimal"
                value={rateForm.base_hourly_rate}
                onChange={(event) => setRateForm((current) => ({ ...current, base_hourly_rate: event.target.value }))}
              />
            </label>
            <label>
              月額固定額
              <input
                inputMode="decimal"
                value={rateForm.fixed_monthly_amount}
                onChange={(event) =>
                  setRateForm((current) => ({ ...current, fixed_monthly_amount: event.target.value }))
                }
              />
            </label>
          </>
        ) : (
          <>
            <label>
              コード
              <input
                value={allowanceForm.code}
                onChange={(event) => setAllowanceForm((current) => ({ ...current, code: event.target.value }))}
              />
            </label>
            <label>
              名称
              <input
                value={allowanceForm.name}
                onChange={(event) => setAllowanceForm((current) => ({ ...current, name: event.target.value }))}
              />
            </label>
            <label>
              手当種別
              <select
                value={allowanceForm.allowance_type}
                onChange={(event) =>
                  setAllowanceForm((current) => ({
                    ...current,
                    allowance_type: event.target.value as LaborCostAllowanceType,
                  }))
                }
              >
                <option value="per_worked_day">勤務日数連動</option>
                <option value="per_worked_hour">勤務時間連動</option>
                <option value="fixed_monthly">月額固定</option>
                <option value="manual">手入力</option>
              </select>
            </label>
            <label>
              金額
              <input
                inputMode="decimal"
                value={allowanceForm.amount}
                onChange={(event) => setAllowanceForm((current) => ({ ...current, amount: event.target.value }))}
              />
            </label>
          </>
        )}
        <label>
          有効開始
          <input
            type="date"
            value={isRates ? rateForm.valid_from : allowanceForm.valid_from}
            onChange={(event) =>
              isRates
                ? setRateForm((current) => ({ ...current, valid_from: event.target.value }))
                : setAllowanceForm((current) => ({ ...current, valid_from: event.target.value }))
            }
          />
        </label>
        <label>
          有効終了
          <input
            type="date"
            value={isRates ? rateForm.valid_to : allowanceForm.valid_to}
            onChange={(event) =>
              isRates
                ? setRateForm((current) => ({ ...current, valid_to: event.target.value }))
                : setAllowanceForm((current) => ({ ...current, valid_to: event.target.value }))
            }
          />
        </label>
        <label>
          メモ
          <input
            value={isRates ? rateForm.notes : allowanceForm.notes}
            onChange={(event) =>
              isRates
                ? setRateForm((current) => ({ ...current, notes: event.target.value }))
                : setAllowanceForm((current) => ({ ...current, notes: event.target.value }))
            }
          />
        </label>
        <div className="actions">
          <button type="submit" disabled={isSubmitting}>
            {editingId ? "更新" : "作成"}
          </button>
          {editingId ? (
            <button type="button" onClick={resetForm}>
              キャンセル
            </button>
          ) : null}
        </div>
      </form>
      {listQuery.isLoading ? <p>読み込み中...</p> : null}
      {listQuery.isError ? <p className="error">一覧の取得に失敗しました。</p> : null}
      {!listQuery.isLoading && listQuery.data?.results.length === 0 ? (
        <p className="subtle-text">登録はありません。</p>
      ) : null}
      {isRates && rates.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>拠点</th>
              <th>スタッフ</th>
              <th>雇用区分</th>
              <th>時給</th>
              <th>月額固定額</th>
              <th>有効期間</th>
              <th>状態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {rates.map((item) => (
              <tr key={item.id}>
                <td>{item.location_name}</td>
                <td>{item.employee_code} {item.staff_display_name}</td>
                <td>{employmentTypeLabel(item.employment_type)}</td>
                <td>{item.base_hourly_rate ?? "-"}</td>
                <td>{item.fixed_monthly_amount ?? "-"}</td>
                <td>{item.valid_from} - {item.valid_to ?? ""}</td>
                <td>{item.is_active ? "有効" : "無効"}</td>
                <td className="actions">
                  <button type="button" onClick={() => editRate(item)}>編集</button>
                  <button type="button" onClick={() => void setActive(item.id, !item.is_active)}>
                    {item.is_active ? "無効化" : "再有効化"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {!isRates && allowances.length ? (
        <table className="table">
          <thead>
            <tr>
              <th>拠点</th>
              <th>スタッフ</th>
              <th>コード</th>
              <th>名称</th>
              <th>種別</th>
              <th>金額</th>
              <th>有効期間</th>
              <th>状態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {allowances.map((item) => (
              <tr key={item.id}>
                <td>{item.location_name}</td>
                <td>{item.employee_code} {item.staff_display_name}</td>
                <td>{item.code}</td>
                <td>{item.name}</td>
                <td>{allowanceTypeLabel(item.allowance_type)}</td>
                <td>{item.amount}</td>
                <td>{item.valid_from} - {item.valid_to ?? ""}</td>
                <td>{item.is_active ? "有効" : "無効"}</td>
                <td className="actions">
                  <button type="button" onClick={() => editAllowance(item)}>編集</button>
                  <button type="button" onClick={() => void setActive(item.id, !item.is_active)}>
                    {item.is_active ? "無効化" : "再有効化"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}
