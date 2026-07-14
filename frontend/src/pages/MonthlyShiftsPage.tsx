import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../features/auth/AuthContext";
import { buildOffsetOptions, offsetToLabel } from "../lib/timeOffsets";
import type {
  Location,
  MonthlyShiftAssignment,
  MonthlyShiftMatrix,
  MonthlyShiftPlan,
  MonthlyShiftPublication,
  MonthlyShiftSegment,
  Paginated,
  PublicationPreview,
  ShiftPattern,
  TemplateGenerationResult,
  WeeklyShiftTemplate,
  WorkArea,
  WorkType,
  WorkTypeAvailability,
} from "../lib/types";

type CellSelection = {
  staff: string;
  staffName: string;
  workDate: string;
  assignmentId?: string;
  inactiveAssignmentId?: string;
  inactivePatternShortName?: string;
};

type SegmentForm = {
  id?: string;
  work_type: string;
  work_area: string | null;
  start_offset_minutes: number;
  end_offset_minutes: number;
  display_order: number;
  notes: string;
};

const today = new Date();
const defaultYear = today.getFullYear();
const defaultMonth = today.getMonth() + 1;
const timeOptions = buildOffsetOptions();

function toSegmentForm(segment: MonthlyShiftSegment): SegmentForm {
  return {
    id: segment.id,
    work_type: segment.work_type,
    work_area: segment.work_area,
    start_offset_minutes: segment.start_offset_minutes,
    end_offset_minutes: segment.end_offset_minutes,
    display_order: segment.display_order,
    notes: segment.notes,
  };
}

function patternSegmentToForm(segment: NonNullable<ShiftPattern["segments"]>[number], index: number): SegmentForm {
  return {
    work_type: segment.work_type,
    work_area: segment.work_area,
    start_offset_minutes: segment.start_offset_minutes,
    end_offset_minutes: segment.end_offset_minutes,
    display_order: (index + 1) * 10,
    notes: segment.notes,
  };
}

type PublicationWarningFingerprintEntry = {
  assignment: string;
  work_date: string;
  staff: string;
  severity: string;
  code: string;
  message: string;
};

const WARNING_UPDATED_MESSAGE = "警告内容が更新されました。最新の警告を確認して、再度チェックしてください。";
const WARNING_REQUIRED_MESSAGE = "警告内容を確認してください。";

function compareText(left: string, right: string) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

function comparePublicationWarning(left: PublicationWarningFingerprintEntry, right: PublicationWarningFingerprintEntry) {
  return (
    compareText(left.assignment, right.assignment) ||
    compareText(left.work_date, right.work_date) ||
    compareText(left.staff, right.staff) ||
    compareText(left.severity, right.severity) ||
    compareText(left.code, right.code) ||
    compareText(left.message, right.message)
  );
}

function publicationWarningFingerprint(preview: PublicationPreview | null): string {
  if (!preview) return "";
  return JSON.stringify(
    preview.items
      .flatMap((item) =>
        item.issues
          .filter((issue) => issue.severity === "warning")
          .map((issue) => ({
            assignment: item.assignment ?? "",
            work_date: item.work_date ?? "",
            staff: item.staff ?? "",
            severity: issue.severity,
            code: issue.code,
            message: issue.message,
          })),
      )
      .sort(comparePublicationWarning),
  );
}

function attendanceStatusLabel(status: string) {
  const labels: Record<string, string> = {
    open: "未打刻",
    clocked_in: "出勤済み",
    on_break: "休憩中",
    clocked_out: "退勤済み",
    pending_correction: "修正申請中",
    confirmed: "確定済み",
    void: "無効",
  };
  return labels[status] ?? status;
}

export function MonthlyShiftsPage() {
  const { user, loading } = useAuth();
  const queryClient = useQueryClient();
  const routerLocation = useLocation();
  const searchParams = useMemo(() => new URLSearchParams(routerLocation.search), [routerLocation.search]);
  const initialYear = Number(searchParams.get("year")) || defaultYear;
  const initialMonth = Number(searchParams.get("month")) || defaultMonth;
  const initialLocation = searchParams.get("location") ?? "";
  const roles = user?.roles ?? [];
  const canManage = roles.includes("system_admin") || roles.includes("shift_manager");
  const canView = canManage || roles.includes("supervisor");
  const [location, setLocation] = useState(initialLocation);
  const [year, setYear] = useState(initialYear);
  const [month, setMonth] = useState(initialMonth);
  const [plan, setPlan] = useState<MonthlyShiftPlan | null>(null);
  const [staffSearch, setStaffSearch] = useState("");
  const [assignedOnly, setAssignedOnly] = useState(false);
  const [selected, setSelected] = useState<CellSelection | null>(null);
  const [assignment, setAssignment] = useState<MonthlyShiftAssignment | null>(null);
  const [selectedPattern, setSelectedPattern] = useState("");
  const [segments, setSegments] = useState<SegmentForm[]>([]);
  const [notes, setNotes] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [existingMode, setExistingMode] = useState<"skip_existing" | "replace_template_generated">("skip_existing");
  const [invalidMode, setInvalidMode] = useState<"strict" | "skip_invalid">("strict");
  const [preview, setPreview] = useState<TemplateGenerationResult | null>(null);
  const [previewKey, setPreviewKey] = useState("");
  const [publicationPreview, setPublicationPreview] = useState<PublicationPreview | null>(null);
  const [acknowledgedWarningFingerprint, setAcknowledgedWarningFingerprint] = useState("");
  const [selectedPublicationId, setSelectedPublicationId] = useState("");
  const [isDirty, setIsDirty] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const processedDeepLinkKey = useRef("");

  const locationQuery = useQuery({
    enabled: canView,
    queryKey: ["locations", "monthly"],
    queryFn: () => api<Paginated<Location>>("/api/v1/locations/?page_size=100&is_active=true"),
  });
  const planQuery = useQuery({
    enabled: canView && Boolean(location),
    queryKey: ["monthly-shift-plans", location, year, month],
    queryFn: () =>
      api<Paginated<MonthlyShiftPlan>>(
        `/api/v1/monthly-shift-plans/?page_size=10&location=${location}&year=${year}&month=${month}&is_active=true`,
      ),
  });
  const deepLinkDate = searchParams.get("date");
  const deepLinkStaff = searchParams.get("staff");
  const hasDeepLink = Boolean(deepLinkDate && deepLinkStaff);
  const activePlan = plan ?? planQuery.data?.results[0] ?? null;
  const matrixQuery = useQuery({
    enabled: canView && Boolean(activePlan),
    queryKey: ["monthly-shift-matrix", activePlan?.id, staffSearch, assignedOnly],
    queryFn: () =>
      api<MonthlyShiftMatrix>(
        `/api/v1/monthly-shift-plans/${activePlan?.id}/matrix/?staff_search=${encodeURIComponent(staffSearch)}${
          assignedOnly ? "&assigned_only=true" : ""
        }`,
      ),
  });
  const patternQuery = useQuery({
    enabled: canView && Boolean(activePlan?.location),
    queryKey: ["shift-patterns", "monthly", activePlan?.location],
    queryFn: () => api<Paginated<ShiftPattern>>(`/api/v1/shift-patterns/?page_size=100&is_active=true&location=${activePlan?.location}`),
  });
  const templateQuery = useQuery({
    enabled: canView && Boolean(activePlan?.location),
    queryKey: ["weekly-shift-templates", "monthly", activePlan?.location],
    queryFn: () =>
      api<Paginated<WeeklyShiftTemplate>>(`/api/v1/weekly-shift-templates/?page_size=100&is_active=true&location=${activePlan?.location}`),
  });
  const workTypeQuery = useQuery({
    enabled: canView && Boolean(activePlan?.location),
    queryKey: ["work-types", "monthly", activePlan?.location],
    queryFn: () => api<Paginated<WorkType>>(`/api/v1/work-types/?page_size=100&is_active=true&location=${activePlan?.location}`),
  });
  const workAreaQuery = useQuery({
    enabled: canView && Boolean(activePlan?.location),
    queryKey: ["work-areas", "monthly", activePlan?.location],
    queryFn: () => api<Paginated<WorkArea>>(`/api/v1/work-areas/?page_size=100&is_active=true&location=${activePlan?.location}`),
  });
  const availabilityQuery = useQuery({
    enabled: canView && Boolean(activePlan?.location),
    queryKey: ["work-type-availabilities", "monthly", activePlan?.location],
    queryFn: () =>
      api<Paginated<WorkTypeAvailability>>(
        `/api/v1/work-type-availabilities/?page_size=200&is_active=true&location=${activePlan?.location}`,
      ),
  });
  const publicationHistoryQuery = useQuery({
    enabled: canView && Boolean(activePlan),
    queryKey: ["monthly-shift-publications", activePlan?.id],
    queryFn: () => api<MonthlyShiftPublication[]>(`/api/v1/monthly-shift-plans/${activePlan?.id}/publications/`),
  });
  const publicationDetailQuery = useQuery({
    enabled: canView && Boolean(selectedPublicationId),
    queryKey: ["monthly-shift-publication", selectedPublicationId],
    queryFn: () => api<MonthlyShiftPublication>(`/api/v1/monthly-shift-publications/${selectedPublicationId}/`),
  });
  useEffect(() => {
    if (!plan && (initialLocation || (location && hasDeepLink)) && planQuery.data?.results[0]) {
      setPlan(planQuery.data.results[0]);
    }
  }, [hasDeepLink, initialLocation, location, plan, planQuery.data]);
  useEffect(() => {
    const targetDate = deepLinkDate;
    const targetStaff = deepLinkStaff;
    if (!targetDate || !targetStaff || !matrixQuery.data) return;
    const key = `${location}|${year}|${month}|${targetDate}|${targetStaff}`;
    if (processedDeepLinkKey.current === key) return;
    const row = matrixQuery.data.rows.find((item) => item.staff === targetStaff);
    if (!row) return;
    if (!matrixQuery.data.dates.some((item) => item.date === targetDate)) return;
    processedDeepLinkKey.current = key;
    const cell = row.assignments[targetDate];
    const inactive = row.inactive_assignments?.[targetDate];
    const nextSelection = {
      staff: row.staff,
      staffName: row.staff_display_name,
      workDate: targetDate,
      assignmentId: cell?.id ?? undefined,
      inactiveAssignmentId: inactive?.id,
      inactivePatternShortName: inactive?.pattern_short_name,
    };
    let cancelled = false;
    if (!cell?.id) {
      setSelected(nextSelection);
      setAssignment(null);
      setSelectedPattern("");
      setSegments([]);
      setNotes("");
      setIsDirty(false);
      return undefined;
    }
    setSelected(nextSelection);
    setError("");
    setMessage("");
    void api<MonthlyShiftAssignment>(`/api/v1/monthly-shift-assignments/${cell.id}/`)
      .then((detail) => {
        if (cancelled) return;
        setAssignment(detail);
        setSelectedPattern(detail.source_shift_pattern ?? "");
        setSegments((detail.segments ?? []).filter((segment) => segment.is_active).map(toSegmentForm));
        setNotes(detail.notes);
        setIsDirty(false);
      })
      .catch((deepLinkError) => {
        if (cancelled) return;
        setSelected(nextSelection);
        setError(deepLinkError instanceof Error ? deepLinkError.message : "勤務詳細の取得に失敗しました。");
      });
    return () => {
      cancelled = true;
    };
  }, [deepLinkDate, deepLinkStaff, location, matrixQuery.data, month, year]);

  const currentPreviewKey = `${activePlan?.id ?? ""}|${templateId}|${existingMode}|${invalidMode}`;
  const planStatus = activePlan?.workflow_status ?? "draft";
  const currentWarningFingerprint = publicationWarningFingerprint(publicationPreview);
  const publicationPreviewKey = publicationPreview
    ? JSON.stringify({
        plan: publicationPreview.plan,
        content_hash: publicationPreview.content_hash,
        confirmed_content_hash: publicationPreview.confirmed_content_hash,
        workflow_status: publicationPreview.workflow_status,
        warning_fingerprint: currentWarningFingerprint,
        error_count: publicationPreview.summary.error_count,
        warning_count: publicationPreview.summary.warning_count,
      })
    : "";
  const warningAcknowledged =
    publicationPreview !== null &&
    publicationPreview.summary.warning_count > 0 &&
    acknowledgedWarningFingerprint === currentWarningFingerprint;
  const warningRequirementSatisfied =
    publicationPreview !== null &&
    (publicationPreview.summary.warning_count === 0 || warningAcknowledged);
  const isPlanEditable =
    canManage && Boolean(activePlan) && (activePlan?.is_editable ?? !["confirmed", "published"].includes(planStatus));
  const lockMessage =
    planStatus === "confirmed"
      ? "この月間シフトは確定済みのため編集できません。"
      : planStatus === "published"
        ? "この月間シフトは公開中のため編集できません。公開停止後に確定解除してください。"
        : "";
  const canConfirmPlan =
    canManage &&
    Boolean(publicationPreview) &&
    publicationPreview?.can_confirm === true &&
    warningRequirementSatisfied &&
    !isSubmitting;
  const canPublishPlan =
    canManage &&
    Boolean(publicationPreview) &&
    publicationPreview?.can_publish === true &&
    warningRequirementSatisfied &&
    !isSubmitting;
  useEffect(() => {
    setAcknowledgedWarningFingerprint("");
  }, [publicationPreviewKey, activePlan?.id, location, month, planStatus, year]);
  const availableWorkTypeIds = useMemo(
    () => new Set((availabilityQuery.data?.results ?? []).map((item) => item.work_type)),
    [availabilityQuery.data?.results],
  );
  const workTypeOptions = useMemo(
    () => (workTypeQuery.data?.results ?? []).filter((item) => availableWorkTypeIds.has(item.id)),
    [availableWorkTypeIds, workTypeQuery.data?.results],
  );
  const publicationHistory = Array.isArray(publicationHistoryQuery.data) ? publicationHistoryQuery.data : [];
  const isWorkTypeAvailableForArea = (workType: string, workArea: string | null) =>
    (availabilityQuery.data?.results ?? []).some(
      (item) => item.work_type === workType && (item.work_area === null || item.work_area === workArea),
    );

  if (loading) return <section className="card monthly-page">読み込み中...</section>;
  if (!canView) return <Navigate to="/403" replace />;

  const changeMonth = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
    setPlan(null);
    setSelected(null);
    setPreview(null);
    setPreviewKey("");
    setPublicationPreview(null);
    setSelectedPublicationId("");
  };

  const openOrCreatePlan = async () => {
    setError("");
    setMessage("");
    const existing = planQuery.data?.results[0];
    if (existing) {
      setPlan(existing);
      setPreview(null);
      setPreviewKey("");
      setPublicationPreview(null);
      setSelectedPublicationId("");
      return;
    }
    if (!canManage) {
      setMessage("この年月の月間表はまだ作成されていません。");
      return;
    }
    try {
      const locationName = locationQuery.data?.results.find((item) => item.id === location)?.name ?? "";
      const created = await api<MonthlyShiftPlan>("/api/v1/monthly-shift-plans/", {
        method: "POST",
        body: JSON.stringify({ location, year, month, name: `${year}年${month}月 ${locationName}シフト`, notes: "" }),
      });
      setPlan(created);
      setPreview(null);
      setPreviewKey("");
      setMessage("月間表を作成しました。");
      await planQuery.refetch();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "月間表の作成に失敗しました。");
    }
  };

  const loadAssignment = async (selection: CellSelection) => {
    if (isDirty && !window.confirm("未保存の変更を破棄しますか？")) return;
    setSelected(selection);
    setError("");
    setMessage("");
    if (!selection.assignmentId) {
      setAssignment(null);
      setSelectedPattern("");
      setSegments([]);
      setNotes("");
      setIsDirty(false);
      return;
    }
    try {
      const detail = await api<MonthlyShiftAssignment>(`/api/v1/monthly-shift-assignments/${selection.assignmentId}/`);
      setAssignment(detail);
      setSelectedPattern(detail.source_shift_pattern ?? "");
      setSegments((detail.segments ?? []).filter((segment) => segment.is_active).map(toSegmentForm));
      setNotes(detail.notes);
      setIsDirty(false);
    } catch (detailError) {
      setError(detailError instanceof Error ? detailError.message : "勤務詳細の取得に失敗しました。");
    }
  };

  const updateSegment = (index: number, patch: Partial<SegmentForm>) => {
    setSegments((current) =>
      current.map((segment, i) => {
        if (i !== index) return segment;
        const next = { ...segment, ...patch };
        if (patch.work_type && next.work_area && !isWorkTypeAvailableForArea(patch.work_type, next.work_area)) {
          next.work_area = null;
        }
        if (Object.prototype.hasOwnProperty.call(patch, "work_area") && next.work_type && !isWorkTypeAvailableForArea(next.work_type, next.work_area)) {
          next.work_type = "";
        }
        return next;
      }),
    );
    setIsDirty(true);
  };

  const addSegment = () => {
    setSegments((current) => [
      ...current,
      { work_type: "", work_area: null, start_offset_minutes: 540, end_offset_minutes: 600, display_order: current.length * 10, notes: "" },
    ]);
    setIsDirty(true);
  };

  const removeSegment = (index: number) => {
    setSegments((current) => current.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  const moveSegment = (index: number, delta: number) => {
    setSegments((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next.map((segment, i) => ({ ...segment, display_order: (i + 1) * 10 }));
    });
    setIsDirty(true);
  };

  const choosePatternWithPreview = async (patternId: string) => {
    if (assignment && patternId && patternId !== selectedPattern && !window.confirm("現在の勤務内訳を選択したパターンで置き換えます。")) {
      return;
    }
    if (!patternId) {
      setSelectedPattern("");
      setSegments([]);
      setIsDirty(true);
      return;
    }
    try {
      const detail = await api<ShiftPattern>(`/api/v1/shift-patterns/${patternId}/`);
      setSegments((detail.segments ?? []).filter((segment) => segment.is_active).map(patternSegmentToForm));
      setSelectedPattern(patternId);
      setIsDirty(true);
    } catch (patternError) {
      setError(patternError instanceof Error ? patternError.message : "勤務パターン詳細の取得に失敗しました。");
    }
  };

  const saveAssignment = async () => {
    if (!selected || !activePlan || !isPlanEditable || isSubmitting) return;
    setIsSubmitting(true);
    setError("");
    try {
      if (assignment) {
        const saved = await api<MonthlyShiftAssignment>(`/api/v1/monthly-shift-assignments/${assignment.id}/`, {
          method: "PATCH",
          body: JSON.stringify({
            notes,
            ...(selectedPattern && selectedPattern !== assignment.source_shift_pattern
              ? { shift_pattern: selectedPattern }
              : { segments }),
          }),
        });
        setAssignment(saved);
        setMessage(saved.warnings?.length ? saved.warnings.map((item) => item.message).join(" / ") : "保存しました。");
      } else {
        const saved = await api<MonthlyShiftAssignment>("/api/v1/monthly-shift-assignments/", {
          method: "POST",
          body: JSON.stringify({
            monthly_shift_plan: activePlan.id,
            work_date: selected.workDate,
            staff: selected.staff,
            shift_pattern: selectedPattern,
            notes,
          }),
        });
        setAssignment(saved);
        setMessage(saved.warnings?.length ? saved.warnings.map((item) => item.message).join(" / ") : "保存しました。");
      }
      setIsDirty(false);
      await matrixQuery.refetch();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const deactivateAssignment = async () => {
    if (!assignment || !isPlanEditable || !window.confirm("勤務を解除しますか？")) return;
    setIsSubmitting(true);
    try {
      await api(`/api/v1/monthly-shift-assignments/${assignment.id}/deactivate/`, { method: "POST", body: JSON.stringify({}) });
      setSelected(null);
      setAssignment(null);
      setMessage("勤務を解除しました。");
      await matrixQuery.refetch();
    } catch (deactivateError) {
      setError(deactivateError instanceof Error ? deactivateError.message : "解除に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const reactivateAssignment = async () => {
    if (!selected?.inactiveAssignmentId || !isPlanEditable || isSubmitting || !window.confirm("解除済み勤務を復元しますか？")) return;
    setIsSubmitting(true);
    setError("");
    try {
      const restored = await api<MonthlyShiftAssignment>(
        `/api/v1/monthly-shift-assignments/${selected.inactiveAssignmentId}/reactivate/`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setAssignment(restored);
      setSelectedPattern(restored.source_shift_pattern ?? "");
      setSegments((restored.segments ?? []).filter((segment) => segment.is_active).map(toSegmentForm));
      setNotes(restored.notes);
      setMessage(restored.warnings?.length ? restored.warnings.map((item) => item.message).join(" / ") : "勤務を復元しました。");
      setIsDirty(false);
      await matrixQuery.refetch();
    } catch (reactivateError) {
      setError(reactivateError instanceof Error ? reactivateError.message : "再有効化に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const previewTemplate = async () => {
    if (!activePlan || !templateId || !isPlanEditable) return;
    setError("");
    try {
      const result = await api<TemplateGenerationResult>(`/api/v1/monthly-shift-plans/${activePlan.id}/preview-template-generation/`, {
        method: "POST",
        body: JSON.stringify({ weekly_shift_template: templateId, existing_mode: existingMode, invalid_mode: invalidMode }),
      });
      setPreview(result);
      setPreviewKey(currentPreviewKey);
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : "生成プレビューに失敗しました。");
    }
  };

  const applyTemplate = async () => {
    if (!activePlan || !templateId || !isPlanEditable || isSubmitting) return;
    if (existingMode === "replace_template_generated" && !window.confirm("テンプレート生成済み勤務を置換します。")) return;
    setIsSubmitting(true);
    setError("");
    try {
      const result = await api<TemplateGenerationResult>(`/api/v1/monthly-shift-plans/${activePlan.id}/apply-template/`, {
        method: "POST",
        body: JSON.stringify({ weekly_shift_template: templateId, existing_mode: existingMode, invalid_mode: invalidMode }),
      });
      setPreview(result);
      setMessage("テンプレートを適用しました。");
      await matrixQuery.refetch();
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : "テンプレート適用に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const loadPublicationPreview = async () => {
    if (!activePlan) return null;
    setError("");
    try {
      const result = await api<PublicationPreview>(`/api/v1/monthly-shift-plans/${activePlan.id}/publication-preview/`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setPublicationPreview(result);
      return result;
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : "公開プレビューに失敗しました。");
      return null;
    }
  };

  const loadLatestPublicationPreviewForAction = async () => {
    if (!activePlan) return null;
    const latestPreview = await api<PublicationPreview>(`/api/v1/monthly-shift-plans/${activePlan.id}/publication-preview/`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setPublicationPreview(latestPreview);
    return latestPreview;
  };

  const confirmPlan = async () => {
    if (!activePlan || !publicationPreview || isSubmitting) return;
    const acknowledgedFingerprint = acknowledgedWarningFingerprint;
    setIsSubmitting(true);
    setError("");
    try {
      const latestPreview = await loadLatestPublicationPreviewForAction();
      if (!latestPreview) return;
      const latestWarningFingerprint = publicationWarningFingerprint(latestPreview);
      if (!latestPreview.can_confirm && latestPreview.summary.error_count === 0) {
        setError("確定できる状態ではありません。公開プレビューを確認してください。");
        return;
      }
      if (latestPreview.summary.error_count > 0) {
        setError("公開プレビューにエラーがあります。エラーを解消してから確定してください。");
        return;
      }
      if (latestPreview.summary.warning_count > 0 && acknowledgedFingerprint !== latestWarningFingerprint) {
        setAcknowledgedWarningFingerprint("");
        setError(acknowledgedFingerprint ? WARNING_UPDATED_MESSAGE : WARNING_REQUIRED_MESSAGE);
        return;
      }
      const result = await api<{ plan: MonthlyShiftPlan; preview: PublicationPreview }>(`/api/v1/monthly-shift-plans/${activePlan.id}/confirm/`, {
        method: "POST",
        body: JSON.stringify({ acknowledge_warnings: latestPreview.summary.warning_count > 0 }),
      });
      setPlan(result.plan);
      setPublicationPreview(result.preview);
      setMessage("月間シフトを確定しました。");
      await publicationHistoryQuery.refetch();
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "確定に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const reopenPlan = async () => {
    if (!activePlan || isSubmitting || !window.confirm("確定を解除しますか？")) return;
    setIsSubmitting(true);
    setError("");
    try {
      const result = await api<MonthlyShiftPlan>(`/api/v1/monthly-shift-plans/${activePlan.id}/reopen/`, {
        method: "POST",
        body: JSON.stringify({ reason: "" }),
      });
      setPlan(result);
      setPublicationPreview(null);
      setMessage("確定を解除しました。");
    } catch (reopenError) {
      setError(reopenError instanceof Error ? reopenError.message : "確定解除に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const publishPlan = async () => {
    if (!activePlan || !publicationPreview || isSubmitting) return;
    const displayedWarningFingerprint = currentWarningFingerprint;
    const acknowledgedFingerprint = acknowledgedWarningFingerprint;
    setIsSubmitting(true);
    setError("");
    try {
      const latestPreview = await loadLatestPublicationPreviewForAction();
      if (!latestPreview) return;
      const latestWarningFingerprint = publicationWarningFingerprint(latestPreview);
      if (displayedWarningFingerprint !== latestWarningFingerprint) {
        setAcknowledgedWarningFingerprint("");
        setError(WARNING_UPDATED_MESSAGE);
        return;
      }
      if (latestPreview.confirmation_stale) {
        setError("確定後にシフト内容が変更されています。確定解除して再度確定してください。");
        return;
      }
      if (latestPreview.summary.error_count > 0) {
        setError("公開プレビューにエラーがあります。エラーを解消してから公開してください。");
        return;
      }
      if (!latestPreview.can_publish) {
        setError("公開できる状態ではありません。公開プレビューを確認してください。");
        return;
      }
      if (latestPreview.summary.warning_count > 0 && acknowledgedFingerprint !== latestWarningFingerprint) {
        setAcknowledgedWarningFingerprint("");
        setError(acknowledgedFingerprint ? WARNING_UPDATED_MESSAGE : WARNING_REQUIRED_MESSAGE);
        return;
      }
      const result = await api<{ plan: MonthlyShiftPlan; preview: PublicationPreview }>(`/api/v1/monthly-shift-plans/${activePlan.id}/publish/`, {
        method: "POST",
        body: JSON.stringify({ acknowledge_warnings: latestPreview.summary.warning_count > 0 }),
      });
      setPlan(result.plan);
      setPublicationPreview(result.preview);
      setMessage("月間シフトを公開しました。");
      await matrixQuery.refetch();
      await publicationHistoryQuery.refetch();
    } catch (publishError) {
      setError(publishError instanceof Error ? publishError.message : "公開に失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  const withdrawPublication = async () => {
    if (!activePlan || isSubmitting) return;
    const reason = window.prompt("公開取り下げ理由を入力してください。");
    if (!reason) return;
    setIsSubmitting(true);
    setError("");
    try {
      const publicationId = activePlan.current_publication?.id;
      const result = await api<{ plan: MonthlyShiftPlan }>(`/api/v1/monthly-shift-plans/${activePlan.id}/withdraw-publication/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setPlan(result.plan);
      setPublicationPreview(null);
      setSelectedPublicationId("");
      setMessage("公開を取り下げました。");
      await queryClient.invalidateQueries({ queryKey: ["monthly-shift-plans"] });
      await queryClient.invalidateQueries({ queryKey: ["monthly-shift-matrix"] });
      await queryClient.invalidateQueries({ queryKey: ["monthly-shift-publications", activePlan.id] });
      if (publicationId) {
        await queryClient.invalidateQueries({ queryKey: ["monthly-shift-publication", publicationId] });
      }
      await queryClient.invalidateQueries({ queryKey: ["my-published-shifts"] });
    } catch (withdrawError) {
      setError(withdrawError instanceof Error ? withdrawError.message : "公開取り下げに失敗しました。");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="card monthly-page">
      <div className="section-header">
        <div><p className="eyebrow">Shift planning</p><h2>月間シフト</h2></div>
      </div>
      <div className="toolbar field-grid">
        <label>拠点<select value={location} onChange={(event) => { setLocation(event.target.value); setPlan(null); setPreview(null); setPreviewKey(""); setPublicationPreview(null); }}><option value="">選択してください</option>{locationQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>年<input type="number" value={year} onChange={(event) => { setYear(Number(event.target.value)); setPlan(null); setPreview(null); setPreviewKey(""); setPublicationPreview(null); }} /></label>
        <label>月<input type="number" min={1} max={12} value={month} onChange={(event) => { setMonth(Number(event.target.value)); setPlan(null); setPreview(null); setPreviewKey(""); setPublicationPreview(null); }} /></label>
        <button type="button" onClick={() => changeMonth(-1)}>前月</button>
        <button type="button" onClick={() => changeMonth(1)}>次月</button>
        <button type="button" disabled={!location} onClick={() => void openOrCreatePlan()}>{planQuery.data?.results[0] ? "月間表を開く" : canManage ? "新規作成" : "月間表なし"}</button>
      </div>
      {activePlan ? (
        <div className="toolbar field-grid">
          <div>
            <strong>状態: {planStatus === "draft" ? "下書き" : planStatus === "confirmed" ? "確定済み" : "公開済み"}</strong>
            {activePlan.current_publication ? <div className="subtle-text">公開 v{activePlan.current_publication.version}</div> : null}
            {lockMessage ? <div className="subtle-text">{lockMessage}</div> : null}
          </div>
          <button type="button" disabled={!activePlan} onClick={() => void loadPublicationPreview()}>公開プレビュー</button>
          {canManage && planStatus === "draft" ? <button type="button" disabled={!canConfirmPlan} onClick={() => void confirmPlan()}>確定</button> : null}
          {canManage && planStatus === "confirmed" ? <button type="button" disabled={isSubmitting} onClick={() => void reopenPlan()}>確定解除</button> : null}
          {canManage && planStatus === "confirmed" ? <button type="button" disabled={!canPublishPlan} onClick={() => void publishPlan()}>公開</button> : null}
          {planStatus === "published" && activePlan.current_publication ? <button type="button" onClick={() => setSelectedPublicationId(activePlan.current_publication?.id ?? "")}>公開内容を確認</button> : null}
          {canManage && planStatus === "published" ? <button type="button" disabled={isSubmitting} onClick={() => void withdrawPublication()}>公開取り下げ</button> : null}
        </div>
      ) : null}
      {canManage ? <div className="toolbar field-grid">
        <label>週間テンプレート<select value={templateId} disabled={!isPlanEditable} onChange={(event) => { setTemplateId(event.target.value); setPreview(null); setPreviewKey(""); }}><option value="">選択してください</option>{templateQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>既存<select disabled={!isPlanEditable} value={existingMode} onChange={(event) => { setExistingMode(event.target.value as typeof existingMode); setPreview(null); setPreviewKey(""); }}><option value="skip_existing">既存を保持</option><option value="replace_template_generated">生成済みを置換</option></select></label>
        <label>不正候補<select disabled={!isPlanEditable} value={invalidMode} onChange={(event) => { setInvalidMode(event.target.value as typeof invalidMode); setPreview(null); setPreviewKey(""); }}><option value="strict">strict</option><option value="skip_invalid">skip_invalid</option></select></label>
        <button type="button" disabled={!templateId || !activePlan || !isPlanEditable} onClick={() => void previewTemplate()}>生成プレビュー</button>
        {canManage ? <button type="button" disabled={!preview || previewKey !== currentPreviewKey || (invalidMode === "strict" && preview.summary.error_count > 0) || isSubmitting || !isPlanEditable} onClick={() => void applyTemplate()}>テンプレート適用</button> : null}
      </div> : null}
      <div className="toolbar field-grid">
        <label>スタッフ検索<input value={staffSearch} onChange={(event) => setStaffSearch(event.target.value)} /></label>
        <label><input type="checkbox" checked={assignedOnly} onChange={(event) => setAssignedOnly(event.target.checked)} /> 勤務ありのみ</label>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {message ? <p className="success">{message}</p> : null}
      {matrixQuery.data?.shift_change_request_summary?.needs_republish ? (
        <section className="inline-alert">
          <h3>変更反映済み</h3>
          <p>変更反映済み。再公開が必要です。</p>
          <p>
            未完了申請 {matrixQuery.data.shift_change_request_summary.open_count} / 反映済み{" "}
            {matrixQuery.data.shift_change_request_summary.applied_count}
          </p>
        </section>
      ) : null}
      {matrixQuery.data?.shift_request_period ? (
        <section className="inline-alert">
          <h3>希望提出期間</h3>
          <p>
            status {matrixQuery.data.shift_request_period.status} / opens_at{" "}
            {matrixQuery.data.shift_request_period.opens_at} / closes_at{" "}
            {matrixQuery.data.shift_request_period.closes_at}
          </p>
          <p>
            対象スタッフ数 {matrixQuery.data.shift_request_period.target_staff_count ?? 0} / draft件数{" "}
            {matrixQuery.data.shift_request_period.draft_count ?? 0} / submitted件数{" "}
            {matrixQuery.data.shift_request_period.submitted_count ?? 0} / returned件数{" "}
            {matrixQuery.data.shift_request_period.returned_count ?? 0} / locked件数{" "}
            {matrixQuery.data.shift_request_period.locked_count ?? 0} / 未作成件数{" "}
            {matrixQuery.data.shift_request_period.not_created_count ?? 0} / 希望item件数{" "}
            {matrixQuery.data.shift_request_period.item_count ?? 0}
          </p>
        </section>
      ) : null}
      {matrixQuery.isError ? <p className="error">月間表の取得に失敗しました。</p> : null}
      {!activePlan ? <p className="subtle-text">拠点と年月を選び、月間表を開いてください。</p> : null}
      {activePlan && matrixQuery.isLoading ? <p>読み込み中...</p> : null}
      <div className="monthly-layout">
        <div className="monthly-grid-wrap">
          <table className="table monthly-grid">
            <thead>
              <tr><th className="sticky-col">スタッフ</th>{matrixQuery.data?.dates.map((item) => <th key={item.date} className={item.is_saturday ? "saturday" : item.is_sunday ? "sunday" : ""}>{item.day}<br />{item.weekday_label}</th>)}</tr>
            </thead>
            <tbody>
              {matrixQuery.data?.rows.map((row) => (
                <tr key={row.staff}>
                  <th className="sticky-col">{row.staff_display_name}<div className="subtle-text">{row.employee_code}</div></th>
                  {matrixQuery.data.dates.map((item) => {
                    const cell = row.assignments[item.date];
                    const inactive = row.inactive_assignments?.[item.date];
                    return (
                      <td key={`${row.staff}-${item.date}`} className={item.is_saturday ? "saturday" : item.is_sunday ? "sunday" : ""}>
                        <button type="button" className="shift-cell" disabled={!cell && !inactive && !isPlanEditable} onClick={() => void loadAssignment({ staff: row.staff, staffName: row.staff_display_name, workDate: item.date, assignmentId: cell?.id ?? undefined, inactiveAssignmentId: inactive?.id, inactivePatternShortName: inactive?.pattern_short_name })}>
                          {cell ? <><strong>{cell.pattern_short_name || "希望"}</strong><span>{cell.start_offset_minutes != null ? offsetToLabel(cell.start_offset_minutes) : ""}~{cell.end_offset_minutes != null ? offsetToLabel(cell.end_offset_minutes) : ""}</span>{cell.is_customized ? <em>調整</em> : null}{cell.warning_count ? <em>警告</em> : null}{cell.issues?.some((issue) => issue.code.startsWith("requested_")) ? <em>希望</em> : null}{cell.shift_change_requests?.length ? <em>変更</em> : null}{cell.attendance ? <em>{attendanceStatusLabel(cell.attendance.status)}</em> : null}{cell.attendance?.warning_count ? <em>勤怠警告</em> : null}</> : inactive ? <span className="subtle-text">解除済み {inactive.pattern_short_name}</span> : <span className="subtle-text">+</span>}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected ? (
          <aside className="edit-panel">
            <h3>{selected.staffName}</h3>
            <p className="subtle-text">{selected.workDate}</p>
            {!assignment && selected.inactiveAssignmentId ? (
              <div className="inline-alert">
                <p>解除済み勤務：{selected.inactivePatternShortName}</p>
                {isPlanEditable ? <button type="button" disabled={isSubmitting} onClick={() => void reactivateAssignment()}>再有効化</button> : null}
              </div>
            ) : null}
            <label>勤務パターン<select disabled={!isPlanEditable} value={selectedPattern} onChange={(event) => void choosePatternWithPreview(event.target.value)}><option value="">選択してください</option>{patternQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            {selectedPattern && segments.length ? <p className="subtle-text">選択パターン: {segments.length} セグメント</p> : null}
            <label>備考<input readOnly={!isPlanEditable} value={notes} onChange={(event) => { setNotes(event.target.value); setIsDirty(true); }} /></label>
            <div className="section-header"><h3>勤務内訳</h3>{isPlanEditable ? <button type="button" onClick={addSegment}>追加</button> : null}</div>
            {segments.map((segment, index) => (
              <div className="segment-editor" key={segment.id ?? index}>
                <label>開始<select disabled={!isPlanEditable} value={segment.start_offset_minutes} onChange={(event) => updateSegment(index, { start_offset_minutes: Number(event.target.value) })}>{timeOptions.filter((item) => item.value < 2880).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                <label>終了<select disabled={!isPlanEditable} value={segment.end_offset_minutes} onChange={(event) => updateSegment(index, { end_offset_minutes: Number(event.target.value) })}>{timeOptions.filter((item) => item.value > 0).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
                <label>業務<select disabled={!isPlanEditable} value={segment.work_type} onChange={(event) => updateSegment(index, { work_type: event.target.value })}><option value="">選択</option>{workTypeOptions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>エリア<select disabled={!isPlanEditable} value={segment.work_area ?? ""} onChange={(event) => updateSegment(index, { work_area: event.target.value || null })}><option value="">全体</option>{workAreaQuery.data?.results.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>備考<input readOnly={!isPlanEditable} value={segment.notes} onChange={(event) => updateSegment(index, { notes: event.target.value })} /></label>
                {isPlanEditable ? <button type="button" disabled={index === 0} onClick={() => moveSegment(index, -1)}>↑</button> : null}
                {isPlanEditable ? <button type="button" disabled={index === segments.length - 1} onClick={() => moveSegment(index, 1)}>↓</button> : null}
                {isPlanEditable ? <button type="button" onClick={() => removeSegment(index)}>削除</button> : null}
              </div>
            ))}
            {isPlanEditable ? <div className="actions"><button type="button" disabled={isSubmitting || (!assignment && !selectedPattern)} onClick={() => void saveAssignment()}>{isSubmitting ? "保存中..." : "保存"}</button>{assignment ? <button type="button" disabled={isSubmitting} onClick={() => void deactivateAssignment()}>勤務解除</button> : null}</div> : null}
            {selected ? (() => {
              const row = matrixQuery.data?.rows.find((item) => item.staff === selected.staff);
              const cell = row?.assignments[selected.workDate];
              const attendance = cell?.attendance;
              return attendance ? (
                <section className="inline-alert">
                  <h3>勤怠</h3>
                  <dl>
                    <dt>状態</dt><dd>{attendanceStatusLabel(attendance.status)}</dd>
                    <dt>実績</dt><dd>{attendance.actual_start_offset_minutes == null || attendance.actual_end_offset_minutes == null ? "-" : `${offsetToLabel(attendance.actual_start_offset_minutes)}~${offsetToLabel(attendance.actual_end_offset_minutes)}`}</dd>
                    <dt>休憩</dt><dd>{attendance.break_minutes}分</dd>
                    <dt>勤務</dt><dd>{attendance.worked_minutes}分</dd>
                    <dt>差異</dt><dd>開始 {attendance.difference_start_minutes ?? "-"} / 終了 {attendance.difference_end_minutes ?? "-"} / 勤務 {attendance.difference_worked_minutes ?? "-"}</dd>
                    <dt>warning</dt><dd>{attendance.warnings.length ? attendance.warnings.map((item) => item.code).join(" / ") : "-"}</dd>
                  </dl>
                </section>
              ) : null;
            })() : null}
            {selected ? (() => {
              const row = matrixQuery.data?.rows.find((item) => item.staff === selected.staff);
              const cell = row?.assignments[selected.workDate];
              const requests = cell?.shift_requests ?? [];
              return requests.length ? (
                <section className="inline-alert">
                  <h3>希望内容</h3>
                  <ul>
                    {requests.map((item) => (
                      <li key={item.id ?? `${item.request_type}-${item.work_date}`}>
                        {item.request_type} {item.work_date ?? ""} {item.start_offset_minutes != null ? `${offsetToLabel(item.start_offset_minutes)}~${offsetToLabel(item.end_offset_minutes ?? item.start_offset_minutes)}` : ""} {item.reason || item.notes}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null;
            })() : null}
            {selected ? (() => {
              const row = matrixQuery.data?.rows.find((item) => item.staff === selected.staff);
              const cell = row?.assignments[selected.workDate];
              const requests = cell?.shift_change_requests ?? [];
              return requests.length ? (
                <section className="inline-alert">
                  <h3>変更申請</h3>
                  <ul>
                    {requests.map((item) => (
                      <li key={item.id}>
                        {item.request_type} / {item.status} / {item.reason || item.manager_note}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null;
            })() : null}
          </aside>
        ) : null}
      </div>
      {publicationPreview ? (
        <section className="preview-panel">
          <h3>公開プレビュー</h3>
          <p>確定時ハッシュ {publicationPreview.confirmed_content_hash || "-"} / 現在ハッシュ {publicationPreview.content_hash} / 内容変更：{publicationPreview.confirmation_stale ? "あり" : "なし"} / 公開予定Version {publicationPreview.next_publication_version}</p>
          {publicationPreview.confirmation_stale ? <p className="error">確定後にシフト内容が変更されています。確定解除して再度確定してください。</p> : null}
          <p>勤務 {publicationPreview.summary.assignment_count} / スタッフ {publicationPreview.summary.staff_count} / セグメント {publicationPreview.summary.segment_count} / 勤務時間 {publicationPreview.summary.work_minutes}分 / 休憩 {publicationPreview.summary.break_minutes}分 / エラー {publicationPreview.summary.error_count} / 警告 {publicationPreview.summary.warning_count}</p>
          <label><input type="checkbox" checked={warningAcknowledged} onChange={(event) => setAcknowledgedWarningFingerprint(event.target.checked ? currentWarningFingerprint : "")} /> 警告内容を確認しました。</label>
          <table className="table"><thead><tr><th>日付</th><th>スタッフ</th><th>勤務</th><th>issue</th></tr></thead><tbody>{publicationPreview.items.slice(0, 80).map((item, index) => <tr key={`${item.assignment ?? item.scope}-${index}`}><td>{item.work_date ?? "-"}</td><td>{item.staff_display_name ?? "-"}</td><td>{item.pattern_short_name ?? "-"}</td><td>{item.issues.map((issue) => `${issue.severity}:${issue.message}`).join(" / ")}</td></tr>)}</tbody></table>
        </section>
      ) : null}
      {activePlan ? (
        <section className="preview-panel">
          <h3>公開履歴</h3>
          {publicationHistoryQuery.isLoading ? <p>読み込み中...</p> : null}
          {publicationHistoryQuery.isError ? <p className="error">公開履歴の取得に失敗しました。</p> : null}
          {!publicationHistoryQuery.isLoading && !publicationHistoryQuery.isError && publicationHistory.length === 0 ? <p className="subtle-text">公開履歴はありません。</p> : null}
          <table className="table">
            <thead><tr><th>Version</th><th>公開日時</th><th>公開者</th><th>状態</th><th>停止日時</th><th>停止者</th><th>停止理由</th><th>Assignment数</th><th>スタッフ数</th><th>Segment数</th><th></th></tr></thead>
            <tbody>
              {publicationHistory.map((item) => (
                <tr key={item.id}>
                  <td>v{item.version}</td>
                  <td>{item.published_at}</td>
                  <td>{item.published_by_display_name}</td>
                  <td>{item.is_active ? "公開中" : "停止済み"}</td>
                  <td>{item.withdrawn_at ?? ""}</td>
                  <td>{item.withdrawn_by_display_name ?? ""}</td>
                  <td>{item.withdrawal_reason}</td>
                  <td>{item.assignment_count}</td>
                  <td>{item.staff_count}</td>
                  <td>{item.segment_count}</td>
                  <td><button type="button" onClick={() => setSelectedPublicationId(item.id)}>詳細</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      {selectedPublicationId && publicationDetailQuery.isLoading ? <section className="preview-panel"><h3>公開詳細</h3><p>読み込み中...</p></section> : null}
      {selectedPublicationId && publicationDetailQuery.isError ? <section className="preview-panel"><h3>公開詳細</h3><p className="error">公開詳細の取得に失敗しました。</p></section> : null}
      {publicationDetailQuery.data ? (
        <section className="preview-panel">
          <h3>公開詳細 v{publicationDetailQuery.data.version}</h3>
          <p>{publicationDetailQuery.data.location_name_snapshot} / {publicationDetailQuery.data.published_at} / {publicationDetailQuery.data.published_by_display_name}</p>
          <table className="table">
            <thead><tr><th>日付</th><th>スタッフ</th><th>勤務</th><th>時間</th><th>内訳</th><th>備考</th></tr></thead>
            <tbody>
              {(publicationDetailQuery.data.assignments ?? []).map((item) => (
                <tr key={item.id}>
                  <td>{item.work_date}</td>
                  <td>{item.staff_display_name_snapshot}</td>
                  <td>{item.pattern_short_name_snapshot || item.pattern_name_snapshot}</td>
                  <td>{item.start_offset_minutes == null || item.end_offset_minutes == null ? "-" : `${offsetToLabel(item.start_offset_minutes)}~${offsetToLabel(item.end_offset_minutes)}`}</td>
                  <td>{item.segments.map((segment) => `${offsetToLabel(segment.start_offset_minutes)}~${offsetToLabel(segment.end_offset_minutes)} ${segment.work_type_name_snapshot}${segment.work_area_name_snapshot ? `（${segment.work_area_name_snapshot}）` : ""}`).join(" / ")}</td>
                  <td>{item.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      {preview ? (
        <section className="preview-panel">
          <h3>生成プレビュー</h3>
          <p>候補 {preview.summary.candidate_count} / 作成 {preview.summary.create_count} / 置換 {preview.summary.replace_count} / 既存スキップ {preview.summary.skip_existing_count} / 保護スキップ {preview.summary.skip_manual_count} / 検証エラースキップ {preview.summary.skip_invalid_count} / エラー {preview.summary.error_count} / 警告 {preview.summary.warning_count}</p>
          {preview.summary.created_count != null ? <p className="success">適用結果: 作成 {preview.summary.created_count} / 置換 {preview.summary.replaced_count} / 既存スキップ {preview.summary.skip_existing_count} / 保護スキップ {preview.summary.skip_manual_count} / 検証エラースキップ {preview.summary.skip_invalid_count} / スキップ合計 {preview.summary.skipped_count}</p> : null}
          <table className="table"><thead><tr><th>日付</th><th>スタッフ</th><th>勤務</th><th>action</th><th>issue</th></tr></thead><tbody>{preview.items.slice(0, 80).map((item) => <tr key={`${item.work_date}-${item.staff}-${item.shift_pattern}`}><td>{item.work_date}</td><td>{item.staff_display_name}</td><td>{item.shift_pattern_short_name}</td><td>{item.action}</td><td>{item.issues.map((issue) => `${issue.severity}:${issue.message}`).join(" / ")}</td></tr>)}</tbody></table>
        </section>
      ) : null}
    </section>
  );
}
