export type User = {
  id: string;
  username: string;
  display_name: string;
  employee_code: string;
  email: string;
  employment_status: string;
  must_change_password: boolean;
  roles: string[];
  permissions: string[];
};

export type Staff = {
  id: string;
  username: string;
  display_name: string;
  employee_code: string;
  email: string;
  employment_status: string;
  hire_date: string | null;
  termination_date: string | null;
  must_change_password: boolean;
  is_active: boolean;
  roles: string[];
};

export type BaseEntity = {
  id: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
};

export type Location = BaseEntity & {
  code: string;
  name: string;
  short_name: string;
  timezone: string;
};

export type WorkArea = BaseEntity & {
  location: string;
  code: string;
  name: string;
  description?: string;
};

export type WorkCategory = BaseEntity & {
  code: string;
  name: string;
  description?: string;
};

export type WorkType = BaseEntity & {
  category: string;
  code: string;
  name: string;
  short_name: string;
  default_duration_minutes: number;
  minimum_staff_count: number;
  maximum_staff_count: number | null;
  color_key: string;
  requires_capability: boolean;
  can_overlap: boolean;
  is_break: boolean;
  is_bookable: boolean;
  requires_customer: boolean;
};

export type WorkTypeAvailability = BaseEntity & {
  work_type: string;
  location: string;
  work_area: string | null;
};

export type ShiftPatternSegment = BaseEntity & {
  work_type: string;
  work_type_name?: string;
  work_type_color_key?: string;
  work_area: string | null;
  work_area_name?: string;
  start_offset_minutes: number;
  end_offset_minutes: number;
  duration_minutes?: number;
  display_order: number;
  notes: string;
};

export type ShiftPattern = BaseEntity & {
  location: string;
  location_name?: string;
  code: string;
  name: string;
  short_name: string;
  description: string;
  display_order: number;
  start_offset_minutes: number | null;
  end_offset_minutes: number | null;
  total_minutes: number | null;
  work_minutes: number;
  break_minutes: number;
  segment_count: number;
  segments?: ShiftPatternSegment[];
};

export type WeeklyShiftTemplateEntry = BaseEntity & {
  weekday: number;
  weekday_label?: string;
  staff: string;
  staff_display_name?: string;
  shift_pattern: string;
  shift_pattern_name?: string;
  shift_pattern_short_name?: string;
  notes: string;
  display_order: number;
};

export type WeeklyShiftTemplate = BaseEntity & {
  location: string;
  location_name?: string;
  code: string;
  name: string;
  description: string;
  display_order: number;
  staff_count: number;
  entry_count: number;
  entries?: WeeklyShiftTemplateEntry[];
};

export type MonthlyShiftSegment = BaseEntity & {
  source_pattern_segment?: string | null;
  work_type: string;
  work_area: string | null;
  work_type_name_snapshot: string;
  work_type_short_name_snapshot: string;
  work_type_color_key_snapshot: string;
  work_type_is_break_snapshot: boolean;
  work_area_name_snapshot: string;
  start_offset_minutes: number;
  end_offset_minutes: number;
  duration_minutes?: number;
  display_order: number;
  notes: string;
};

export type MonthlyShiftAssignment = BaseEntity & {
  monthly_shift_plan: string;
  work_date: string;
  staff: string;
  staff_display_name?: string;
  source_type: "template" | "manual";
  source_shift_pattern: string | null;
  pattern_name_snapshot: string;
  pattern_short_name_snapshot: string;
  notes: string;
  is_customized: boolean;
  start_offset_minutes: number | null;
  end_offset_minutes: number | null;
  work_minutes: number;
  break_minutes: number;
  segment_count: number;
  warnings?: Array<{ severity: string; code: string; message: string }>;
  segments?: MonthlyShiftSegment[];
};

export type MonthlyShiftPlan = BaseEntity & {
  location: string;
  location_name?: string;
  year: number;
  month: number;
  name: string;
  notes?: string;
  assignment_count: number;
  staff_count: number;
  source_weekly_template: string | null;
  source_weekly_template_name?: string;
  last_generated_at: string | null;
  workflow_status: "draft" | "confirmed" | "published";
  confirmed_at: string | null;
  confirmed_by: string | null;
  confirmed_by_display_name?: string;
  confirmed_content_hash: string;
  is_editable: boolean;
  current_publication: {
    id: string;
    version: number;
    published_at: string;
    published_by: string;
    published_by_display_name: string;
  } | null;
  publication_count: number;
};

export type MonthlyMatrixAssignment = {
  id: string | null;
  pattern_short_name: string;
  start_offset_minutes: number | null;
  end_offset_minutes: number | null;
  source_type: "template" | "manual" | "";
  is_customized: boolean;
  warning_count: number;
  issues?: Array<{ severity: "info" | "warning" | "error"; code: string; message: string }>;
  shift_requests?: ShiftRequestItem[];
  shift_change_requests?: ShiftChangeRequestSummary[];
  attendance?: AttendanceSummary | null;
};

export type MonthlyMatrixInactiveAssignment = {
  id: string;
  pattern_short_name: string;
};

export type MonthlyShiftMatrix = {
  plan: Pick<MonthlyShiftPlan, "id" | "location" | "year" | "month" | "name"> & { location_name: string };
  shift_request_period: ShiftRequestPeriod | null;
  shift_change_request_summary?: {
    open_count: number;
    applied_count: number;
    needs_republish: boolean;
  };
  dates: Array<{
    date: string;
    day: number;
    weekday: number;
    weekday_label: string;
    is_saturday: boolean;
    is_sunday: boolean;
  }>;
  rows: Array<{
    staff: string;
    staff_display_name: string;
    employee_code: string;
    assignments: Record<string, MonthlyMatrixAssignment>;
    inactive_assignments: Record<string, MonthlyMatrixInactiveAssignment>;
  }>;
};

export type TimelineSegment = {
  id: string;
  work_type: string;
  work_area: string | null;
  work_type_name: string;
  work_type_short_name: string;
  work_type_color_key: string;
  work_type_is_break: boolean;
  work_area_name: string;
  start_offset_minutes: number;
  end_offset_minutes: number;
  duration_minutes: number;
  display_order: number;
  notes: string;
  lane: number;
  lane_count: number;
};

export type TimelineAssignment = {
  id: string;
  pattern_name: string;
  pattern_short_name: string;
  source_type: "template" | "manual";
  is_customized: boolean;
  notes: string;
  warning_count: number;
  attendance?: AttendanceSummary | null;
};

export type ShiftTimelineResponse = {
  plan: Pick<MonthlyShiftPlan, "id" | "location" | "year" | "month" | "name"> & { location_name: string };
  range: {
    date_from: string;
    date_to: string;
    day_count: number;
    earliest_start_offset: number | null;
    latest_end_offset: number | null;
    suggested_start_offset: number;
    suggested_end_offset: number;
  };
  dates: MonthlyShiftMatrix["dates"];
  rows: Array<{
    staff: string;
    staff_display_name: string;
    employee_code: string;
    days: Record<string, { assignment: TimelineAssignment | null; segments: TimelineSegment[] }>;
  }>;
  legend: Array<{
    work_type: string;
    name: string;
    short_name: string;
    color_key: string;
    is_break: boolean;
  }>;
  summary: {
    staff_count: number;
    assignment_count: number;
    segment_count: number;
    work_minutes: number;
    break_minutes: number;
  };
};

export type TemplateGenerationResult = {
  summary: {
    candidate_count: number;
    create_count: number;
    replace_count: number;
    skip_existing_count: number;
    skip_manual_count: number;
    skip_invalid_count: number;
    error_count: number;
    warning_count: number;
    created_count?: number;
    replaced_count?: number;
    skipped_count?: number;
  };
  items: Array<{
    work_date: string;
    staff: string;
    staff_display_name: string;
    shift_pattern: string;
    shift_pattern_short_name: string;
    action: string;
    issues: Array<{ severity: "error" | "warning"; code: string; message: string }>;
  }>;
};

export type PublicationPreview = {
  plan: string;
  workflow_status: "draft" | "confirmed" | "published";
  content_hash: string;
  confirmed_content_hash: string;
  confirmation_stale: boolean;
  next_publication_version: number;
  validation_fingerprint: string;
  summary: {
    assignment_count: number;
    staff_count: number;
    segment_count: number;
    work_minutes: number;
    break_minutes: number;
    error_count: number;
    warning_count: number;
  };
  items: Array<{
    scope: string;
    assignment?: string;
    work_date?: string;
    staff?: string;
    staff_display_name?: string;
    pattern_short_name?: string;
    warning_count?: number;
    segment_count?: number;
    issues: Array<{ severity: "error" | "warning"; code: string; message: string }>;
  }>;
  can_confirm: boolean;
  can_publish: boolean;
};

export type MonthlyShiftPublicationSegment = {
  id: string;
  source_segment: string;
  work_type: string;
  work_area: string | null;
  work_type_name_snapshot: string;
  work_type_short_name_snapshot: string;
  work_type_color_key_snapshot: string;
  work_type_is_break_snapshot: boolean;
  work_area_name_snapshot: string;
  start_offset_minutes: number;
  end_offset_minutes: number;
  duration_minutes: number;
  display_order: number;
  notes: string;
};

export type MonthlyShiftPublicationAssignment = {
  id: string;
  source_assignment: string;
  work_date: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  source_type: "template" | "manual";
  is_customized: boolean;
  pattern_code_snapshot: string;
  pattern_name_snapshot: string;
  pattern_short_name_snapshot: string;
  notes: string;
  display_order: number;
  warning_count_snapshot: number;
  start_offset_minutes: number | null;
  end_offset_minutes: number | null;
  work_minutes: number;
  break_minutes: number;
  segments: MonthlyShiftPublicationSegment[];
};

export type MonthlyShiftPublication = {
  id: string;
  monthly_shift_plan: string;
  version: number;
  content_hash: string;
  location: string;
  location_name_snapshot: string;
  location_short_name_snapshot: string;
  year: number;
  month: number;
  plan_name_snapshot: string;
  plan_notes_snapshot: string;
  published_by: string;
  published_by_display_name: string;
  published_at: string;
  withdrawn_by: string | null;
  withdrawn_by_display_name?: string | null;
  withdrawn_at: string | null;
  withdrawal_reason: string;
  is_active: boolean;
  assignment_count: number;
  staff_count: number;
  segment_count: number;
  assignments?: MonthlyShiftPublicationAssignment[];
};

export type MyPublishedShift = {
  id: string;
  source_assignment: string;
  work_date: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  source_type: "template" | "manual";
  is_customized: boolean;
  pattern_code_snapshot: string;
  pattern_name_snapshot: string;
  pattern_short_name_snapshot: string;
  notes: string;
  display_order: number;
  warning_count_snapshot: number;
  start_offset_minutes: number | null;
  end_offset_minutes: number | null;
  work_minutes: number;
  break_minutes: number;
  segments: MonthlyShiftPublicationSegment[];
  shift_change_requests: ShiftChangeRequestSummary[];
  attendance: AttendanceSummary | null;
  publication: {
    id: string;
    version: number;
    monthly_shift_plan: string;
    location: string;
    location_name: string;
    year: number;
    month: number;
    published_at: string;
  };
  is_month_closed: boolean;
  closing_period: { id: string; name: string; status: string } | null;
};

export type AttendanceStatus =
  | "open"
  | "clocked_in"
  | "on_break"
  | "clocked_out"
  | "pending_correction"
  | "confirmed"
  | "void";

export type AttendanceSource = "scheduled" | "unscheduled" | "manual" | "corrected" | "imported";

export type AttendanceWarning = {
  code: string;
  message: string;
};

export type AttendanceSummary = {
  id: string;
  status: AttendanceStatus;
  source: AttendanceSource;
  actual_start_offset_minutes: number | null;
  actual_end_offset_minutes: number | null;
  break_minutes: number;
  worked_minutes: number;
  difference_start_minutes: number | null;
  difference_end_minutes: number | null;
  difference_worked_minutes: number | null;
  warning_count: number;
  warnings: AttendanceWarning[];
  confirmed_at: string | null;
  is_month_closed?: boolean;
  closing_period?: string | null;
  closing_period_name?: string;
};

export type AttendanceEvent = {
  id: string;
  attendance_record: string;
  event_type:
    | "clock_in"
    | "break_start"
    | "break_end"
    | "clock_out"
    | "manual_adjustment"
    | "correction_applied"
    | "voided"
    | "confirmed"
    | "unconfirmed";
  occurred_at: string;
  offset_minutes: number;
  source: "self" | "manager" | "system";
  actor: string;
  actor_display_name: string;
  note: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AttendanceCorrectionRequest = {
  id: string;
  attendance_record: string;
  location: string;
  location_name: string;
  work_date: string;
  staff: string;
  staff_display_name: string;
  requester: string;
  requester_display_name: string;
  status: "draft" | "submitted" | "approved" | "rejected" | "cancelled" | "applied";
  requested_clock_in_at: string | null;
  requested_clock_out_at: string | null;
  requested_break_minutes: number | null;
  requested_staff_note: string;
  reason: string;
  manager_note: string;
  submitted_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  approved_by_display_name?: string | null;
  rejected_at: string | null;
  rejected_by: string | null;
  rejected_by_display_name?: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  cancelled_by_display_name?: string | null;
  applied_at: string | null;
  applied_by: string | null;
  applied_by_display_name?: string | null;
  can_edit: boolean;
  can_submit: boolean;
  can_cancel: boolean;
  can_approve: boolean;
  can_apply: boolean;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type AttendanceClosingStatus = "draft" | "review" | "closed" | "reopened" | "archived";

export type AttendanceClosingPeriod = {
  id: string;
  location: string;
  location_name: string;
  location_code: string;
  year: number;
  month: number;
  name: string;
  description: string;
  status: AttendanceClosingStatus;
  content_hash: string;
  validation_fingerprint: string;
  closed_at: string | null;
  closed_by: string | null;
  closed_by_display_name: string;
  reopened_at: string | null;
  reopened_by: string | null;
  reopened_by_display_name: string;
  snapshot_count: number;
  staff_summary_count: number;
  labor_cost_estimate_period: string | null;
  labor_cost_estimate_status: string;
  labor_cost_estimate_name: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type AttendanceClosingIssue = {
  severity: "warning" | "error";
  code: string;
  message: string;
};

export type AttendanceClosingPreviewItem = {
  attendance_record: string | null;
  location: string;
  location_name: string;
  staff: string;
  staff_display_name: string;
  employee_code: string;
  work_date: string;
  status: AttendanceStatus;
  source: AttendanceSource;
  scheduled_start_offset_minutes: number | null;
  scheduled_end_offset_minutes: number | null;
  actual_clock_in_at: string | null;
  actual_clock_out_at: string | null;
  actual_start_offset_minutes: number | null;
  actual_end_offset_minutes: number | null;
  break_minutes: number;
  worked_minutes: number;
  difference_start_minutes: number | null;
  difference_end_minutes: number | null;
  difference_worked_minutes: number | null;
  warning_count: number;
  warnings: AttendanceClosingIssue[];
  errors: AttendanceClosingIssue[];
  issues: AttendanceClosingIssue[];
  manager_note: string;
  staff_note: string;
  confirmed_at: string | null;
};

export type AttendanceClosingStaffSummary = {
  id?: string;
  closing_period?: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  scheduled_days: number;
  attendance_record_days: number;
  worked_days: number;
  unscheduled_work_days: number;
  scheduled_minutes: number;
  worked_minutes: number;
  break_minutes: number;
  late_count: number;
  early_leave_count: number;
  missing_clock_in_count: number;
  missing_clock_out_count: number;
  open_break_count: number;
  warning_count: number;
  confirmed_count: number;
  unconfirmed_count: number;
  pending_correction_count: number;
};

export type AttendanceClosingRecordSnapshot = {
  id: string;
  closing_period: string;
  attendance_record: string | null;
  location: string;
  location_name_snapshot: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  work_date: string;
  status_snapshot: AttendanceStatus;
  source_snapshot: AttendanceSource;
  scheduled_start_offset_minutes: number | null;
  scheduled_end_offset_minutes: number | null;
  actual_clock_in_at: string | null;
  actual_clock_out_at: string | null;
  actual_start_offset_minutes: number | null;
  actual_end_offset_minutes: number | null;
  break_minutes: number;
  worked_minutes: number;
  difference_start_minutes: number | null;
  difference_end_minutes: number | null;
  difference_worked_minutes: number | null;
  warning_count: number;
  warnings: AttendanceWarning[];
  manager_note_snapshot: string;
  staff_note_snapshot: string;
  confirmed_at: string | null;
};

export type AttendanceClosingPreview = {
  period: string | null;
  location: string;
  year: number;
  month: number;
  status: AttendanceClosingStatus | "live";
  content_hash: string;
  validation_fingerprint: string;
  summary: {
    date_from: string;
    date_to: string;
    snapshot_count: number;
    staff_summary_count: number;
    staff_count: number;
    attendance_record_count: number;
    scheduled_count: number;
    warning_count: number;
    error_count: number;
    worked_minutes: number;
    break_minutes: number;
  };
  items: AttendanceClosingPreviewItem[];
  staff_summaries: AttendanceClosingStaffSummary[];
  can_close: boolean;
};

export type MyAttendanceMonthlyItem = {
  period: string | null;
  location: string;
  location_name: string;
  year: number;
  month: number;
  status: AttendanceClosingStatus | "live";
  is_closed: boolean;
  summary: AttendanceClosingStaffSummary | null;
  daily: Array<AttendanceClosingPreviewItem | AttendanceClosingRecordSnapshot>;
  warnings: AttendanceWarning[];
};

export type MyAttendanceMonthlyResponse = {
  results: MyAttendanceMonthlyItem[];
  count: number;
};

export type LaborCostEmploymentType = "hourly" | "monthly_fixed" | "other";
export type LaborCostAllowanceType = "per_worked_day" | "per_worked_hour" | "fixed_monthly" | "manual";
export type LaborCostEstimateStatus = "draft" | "review" | "finalized" | "reopened" | "archived";

export type StaffCompensationProfile = {
  id: string;
  location: string;
  location_name: string;
  location_code: string;
  staff: string;
  staff_display_name: string;
  employee_code: string;
  employment_type: LaborCostEmploymentType;
  base_hourly_rate: string | null;
  fixed_monthly_amount: string | null;
  valid_from: string;
  valid_to: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type StaffAllowanceAssignment = {
  id: string;
  location: string;
  location_name: string;
  location_code: string;
  staff: string;
  staff_display_name: string;
  employee_code: string;
  code: string;
  name: string;
  allowance_type: LaborCostAllowanceType;
  amount: string;
  valid_from: string;
  valid_to: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type LaborCostIssue = {
  severity: "warning" | "error";
  code: string;
  message: string;
  staff?: string;
  work_date?: string;
  source_assignment?: string;
  relevant_id?: string;
};

export type LaborCostBudgetStatus = "draft" | "review" | "approved" | "reopened" | "archived";
export type LaborCostBudgetThresholdStatus = "normal" | "warning" | "critical";

export type LaborCostBudgetPeriod = {
  id: string;
  location: string;
  location_name: string;
  location_code: string;
  year: number;
  month: number;
  name: string;
  description: string;
  budget_amount: string;
  warning_threshold_percent: string;
  critical_threshold_percent: string;
  source_monthly_shift_plan: string | null;
  source_monthly_shift_plan_name: string;
  source_publication: string | null;
  source_publication_version: number | null;
  status: LaborCostBudgetStatus;
  content_hash: string;
  validation_fingerprint: string;
  approved_at: string | null;
  approved_by: string | null;
  approved_by_display_name: string;
  reopened_at: string | null;
  reopened_by: string | null;
  reopened_by_display_name: string;
  plan_record_snapshot_count: number;
  staff_summary_count: number;
  daily_summary_count: number;
  allowance_snapshot_count: number;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type LaborCostBudgetPlanRecord = {
  id?: string;
  budget_period?: string;
  location: string;
  location_code?: string;
  location_name?: string;
  location_code_snapshot?: string;
  location_name_snapshot?: string;
  staff: string;
  staff_display_name?: string;
  staff_display_name_snapshot?: string;
  employee_code?: string;
  employee_code_snapshot?: string;
  work_date: string;
  monthly_shift_plan: string | null;
  monthly_shift_assignment: string | null;
  publication: string | null;
  publication_assignment: string | null;
  plan_source_snapshot: string;
  employment_type_snapshot: string;
  base_hourly_rate_snapshot: string | null;
  fixed_monthly_amount_snapshot: string | null;
  planned_start_offset_minutes: number | null;
  planned_end_offset_minutes: number | null;
  planned_worked_minutes: number;
  planned_hours_decimal: string;
  planned_base_pay: string;
  planned_daily_allowance: string;
  planned_total: string;
  warning_count: number;
  warnings: LaborCostIssue[];
  error_count: number;
  errors: LaborCostIssue[];
};

export type LaborCostBudgetStaffSummary = {
  id?: string;
  budget_period?: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  employment_type_snapshot: string;
  base_hourly_rate_snapshot: string | null;
  fixed_monthly_amount_snapshot: string | null;
  planned_worked_days: number;
  planned_worked_minutes: number;
  planned_hours_decimal: string;
  planned_hourly_base_pay: string;
  planned_fixed_monthly_pay: string;
  planned_allowance_total: string;
  planned_total: string;
  actual_worked_minutes: number;
  actual_base_pay_total: string;
  actual_allowance_total: string;
  actual_estimated_total: string;
  actual_plan_variance_amount: string;
  actual_plan_variance_percent: string | null;
  warning_count: number;
  error_count: number;
};

export type LaborCostBudgetDailySummary = {
  id?: string;
  budget_period?: string;
  work_date: string;
  planned_staff_count: number;
  planned_worked_minutes: number;
  planned_total: string;
  actual_staff_count: number;
  actual_worked_minutes: number;
  actual_estimated_total: string;
  actual_plan_variance_amount: string;
  actual_plan_variance_percent: string | null;
  warning_count: number;
  error_count: number;
};

export type LaborCostBudgetAllowanceSnapshot = {
  id?: string;
  budget_period?: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  allowance_assignment: string | null;
  code_snapshot: string;
  name_snapshot: string;
  allowance_type_snapshot: string;
  amount_snapshot: string;
  quantity: string;
  planned_amount: string;
  warning_count: number;
  warnings: LaborCostIssue[];
};

export type LaborCostBudgetPreview = {
  period: string;
  location: string;
  location_name: string;
  location_code: string;
  year: number;
  month: number;
  status: LaborCostBudgetStatus;
  plan_source: "published" | "confirmed" | "draft" | "unavailable";
  source_monthly_shift_plan: string | null;
  source_publication: string | null;
  source_content_hash?: string;
  actual_source_status: string;
  actual_estimate_period: string | null;
  actual_content_hash: string;
  content_hash: string;
  validation_fingerprint: string;
  approval_issues: LaborCostIssue[];
  comparison_issues: LaborCostIssue[];
  summary: {
    budget_amount: string;
    planned_total: string;
    actual_estimated_total: string;
    planned_budget_variance_amount: string;
    planned_budget_variance_percent: string | null;
    actual_budget_variance_amount: string;
    actual_budget_variance_percent: string | null;
    actual_plan_variance_amount: string;
    actual_plan_variance_percent: string | null;
    planned_budget_ratio_percent: string | null;
    actual_budget_ratio_percent: string | null;
    planned_budget_status: LaborCostBudgetThresholdStatus;
    actual_budget_status: LaborCostBudgetThresholdStatus;
    plan_record_count: number;
    staff_summary_count: number;
    daily_summary_count: number;
    allowance_snapshot_count: number;
    planned_worked_minutes?: number;
    approval_warning_count?: number;
    approval_error_count?: number;
    comparison_warning_count?: number;
    comparison_error_count?: number;
  };
  plan_records: LaborCostBudgetPlanRecord[];
  staff_summaries: LaborCostBudgetStaffSummary[];
  daily_summaries: LaborCostBudgetDailySummary[];
  allowance_snapshots: LaborCostBudgetAllowanceSnapshot[];
  can_approve: boolean;
};

export type LaborCostEstimatePeriod = {
  id: string;
  location: string;
  location_name: string;
  location_code: string;
  year: number;
  month: number;
  attendance_closing_period: string | null;
  attendance_closing_period_name: string;
  attendance_closing_period_status: string;
  name: string;
  description: string;
  status: LaborCostEstimateStatus;
  content_hash: string;
  validation_fingerprint: string;
  finalized_at: string | null;
  finalized_by: string | null;
  finalized_by_display_name: string;
  reopened_at: string | null;
  reopened_by: string | null;
  reopened_by_display_name: string;
  record_snapshot_count: number;
  staff_summary_count: number;
  allowance_snapshot_count: number;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type LaborCostEstimateRecordSnapshot = {
  id?: string;
  estimate_period?: string;
  attendance_closing_snapshot: string | null;
  attendance_record: string | null;
  location: string;
  location_code?: string;
  location_name?: string;
  location_code_snapshot?: string;
  location_name_snapshot?: string;
  staff: string;
  staff_display_name?: string;
  staff_display_name_snapshot?: string;
  employee_code?: string;
  employee_code_snapshot?: string;
  work_date: string;
  employment_type_snapshot: string;
  base_hourly_rate_snapshot: string | null;
  fixed_monthly_amount_snapshot: string | null;
  worked_minutes: number;
  worked_hours_decimal: string;
  base_pay: string;
  allowance_total: string;
  estimated_total: string;
  warning_count: number;
  warnings: LaborCostIssue[];
  error_count: number;
  errors: LaborCostIssue[];
};

export type LaborCostEstimateStaffSummary = {
  id?: string;
  estimate_period?: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  employment_type_snapshot: string;
  base_hourly_rate_snapshot: string | null;
  fixed_monthly_amount_snapshot: string | null;
  worked_days: number;
  worked_minutes: number;
  worked_hours_decimal: string;
  base_pay_total: string;
  allowance_total: string;
  estimated_total: string;
  warning_count: number;
  error_count: number;
};

export type LaborCostEstimateAllowanceSnapshot = {
  id?: string;
  estimate_period?: string;
  staff: string;
  staff_display_name_snapshot: string;
  employee_code_snapshot: string;
  allowance_assignment: string | null;
  code_snapshot: string;
  name_snapshot: string;
  allowance_type_snapshot: string;
  amount_snapshot: string;
  quantity: string;
  estimated_amount: string;
  warning_count: number;
  warnings: LaborCostIssue[];
};

export type LaborCostEstimatePreview = {
  period: string;
  location: string;
  location_name: string;
  location_code: string;
  year: number;
  month: number;
  status: LaborCostEstimateStatus;
  attendance_closing_period: string | null;
  attendance_closing_status: string;
  source_status: "closed" | "live";
  content_hash: string;
  validation_fingerprint: string;
  summary: {
    date_from: string;
    date_to: string;
    record_snapshot_count: number;
    staff_summary_count: number;
    allowance_snapshot_count: number;
    staff_count: number;
    warning_count: number;
    error_count: number;
    worked_minutes: number;
    worked_hours_decimal: string;
    base_pay_total: string;
    allowance_total: string;
    estimated_total: string;
  };
  issues: LaborCostIssue[];
  record_snapshots: LaborCostEstimateRecordSnapshot[];
  staff_summaries: LaborCostEstimateStaffSummary[];
  allowance_snapshots: LaborCostEstimateAllowanceSnapshot[];
  can_finalize: boolean;
};

export type AttendanceRecord = AttendanceSummary & {
  location: string;
  location_name: string;
  staff: string;
  staff_display_name: string;
  employee_code: string;
  work_date: string;
  monthly_shift_plan: string | null;
  monthly_shift_assignment: string | null;
  publication: string | null;
  publication_assignment: string | null;
  scheduled_start_offset_minutes: number | null;
  scheduled_end_offset_minutes: number | null;
  scheduled_pattern_name_snapshot: string;
  scheduled_pattern_short_name_snapshot: string;
  actual_clock_in_at: string | null;
  actual_clock_out_at: string | null;
  manager_note: string;
  staff_note: string;
  confirmed_by: string | null;
  confirmed_by_display_name?: string | null;
  events: AttendanceEvent[];
  correction_requests: AttendanceCorrectionRequest[];
  can_clock_in: boolean;
  can_break_start: boolean;
  can_break_end: boolean;
  can_clock_out: boolean;
  can_request_correction: boolean;
  can_manage: boolean;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type MyPublishedShiftsResponse = {
  range: {
    date_from: string;
    date_to: string;
  };
  dates: Array<{
    date: string;
    weekday: number;
    weekday_label: string;
    is_saturday: boolean;
    is_sunday: boolean;
  }>;
  shifts: MyPublishedShift[];
};

export type ShiftChangeRequestSummary = {
  id: string;
  request_type: ShiftChangeRequest["request_type"];
  status: ShiftChangeRequest["status"];
  priority: ShiftChangeRequest["priority"];
  requested_staff: string | null;
  requested_staff_display_name: string;
  requested_work_date: string | null;
  requested_start_offset_minutes: number | null;
  requested_end_offset_minutes: number | null;
  reason: string;
  manager_note: string;
  applied_at: string | null;
};

export type ShiftChangeRequest = {
  id: string;
  location: string;
  location_name: string;
  monthly_shift_plan: string;
  publication: string;
  publication_version: number;
  publication_assignment: string | null;
  requester: string;
  requester_display_name: string;
  target_staff: string;
  target_staff_display_name: string;
  requested_staff: string | null;
  requested_staff_display_name: string;
  request_type:
    | "drop_shift"
    | "swap_shift"
    | "cover_request"
    | "change_time"
    | "change_assignment"
    | "manager_adjustment"
    | "note";
  status: "draft" | "submitted" | "approved" | "rejected" | "cancelled" | "applied" | "closed";
  priority: "high" | "normal" | "low";
  work_date: string;
  original_start_offset_minutes: number | null;
  original_end_offset_minutes: number | null;
  original_pattern_name_snapshot: string;
  original_pattern_short_name_snapshot: string;
  requested_work_date: string | null;
  requested_shift_pattern: string | null;
  requested_shift_pattern_name: string;
  requested_start_offset_minutes: number | null;
  requested_end_offset_minutes: number | null;
  requested_notes: string;
  reason: string;
  manager_note: string;
  submitted_at: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  cancelled_at: string | null;
  applied_at: string | null;
  can_edit: boolean;
  can_submit: boolean;
  can_cancel: boolean;
  can_approve: boolean;
  can_apply: boolean;
  created_at: string;
  updated_at: string;
  is_active: boolean;
};

export type ShiftRequestPeriod = {
  id: string;
  location: string;
  location_name: string;
  year: number;
  month: number;
  name: string;
  description: string;
  opens_at: string;
  closes_at: string;
  status: "draft" | "open" | "closed" | "archived";
  draft_count?: number;
  submitted_count?: number;
  returned_count?: number;
  locked_count?: number;
  submission_count?: number;
  item_count?: number;
  target_staff_count?: number;
  not_created_count?: number;
  my_submission?: {
    id: string;
    status: ShiftRequestSubmission["status"];
    submitted_at: string | null;
    item_count: number;
    can_edit: boolean;
    can_submit: boolean;
  } | null;
  is_active: boolean;
};

export type ShiftRequestItem = {
  id?: string;
  request_type: "day_off" | "unavailable" | "prefer_work" | "prefer_time" | "note";
  work_date: string | null;
  start_offset_minutes: number | null;
  end_offset_minutes: number | null;
  work_type: string | null;
  work_type_name?: string;
  work_area: string | null;
  work_area_name?: string;
  priority: "high" | "normal" | "low";
  reason: string;
  notes: string;
  is_active?: boolean;
};

export type ShiftRequestSubmission = {
  id: string;
  request_period: string;
  period: Pick<ShiftRequestPeriod, "id" | "location" | "location_name" | "year" | "month" | "name" | "status" | "opens_at" | "closes_at">;
  staff: string;
  staff_display_name: string;
  status: "draft" | "submitted" | "returned" | "locked";
  can_edit: boolean;
  can_submit: boolean;
  submitted_at: string | null;
  returned_at: string | null;
  return_reason: string;
  notes: string;
  item_count?: number;
  day_off_count?: number;
  unavailable_count?: number;
  prefer_count?: number;
  has_note?: boolean;
  items: ShiftRequestItem[];
};

export type StaffLocation = BaseEntity & {
  staff: string;
  staff_display_name?: string;
  location: string;
  location_name?: string;
  is_primary: boolean;
  valid_from: string;
  valid_until: string | null;
};

export type StaffCapability = BaseEntity & {
  staff: string;
  staff_display_name?: string;
  work_type: string;
  work_type_name?: string;
  location: string | null;
  location_name?: string;
  level: string;
  valid_from: string;
  valid_until: string | null;
  approved_by: string | null;
  approved_by_display_name?: string;
  approved_at?: string | null;
  notes: string;
};

export type MyStaffLocation = {
  id: string;
  location_name: string;
  is_primary: boolean;
  valid_from: string;
  valid_until: string | null;
  is_active: boolean;
};

export type MyCapability = {
  id: string;
  work_type_name: string;
  location_name: string;
  level: string;
  valid_from: string;
  valid_until: string | null;
  approved_by_display_name: string;
  approved_at?: string | null;
  notes: string;
  is_active: boolean;
};

export type RevenueIssue = {
  severity: "warning" | "error";
  code: string;
  message: string;
  category?: string;
  related_period_id?: string;
};

export type RevenueCategory = {
  id: string;
  location: string;
  location_name: string;
  code: string;
  name: string;
  short_name: string;
  description: string;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type RevenueBudgetPeriod = {
  id: string;
  location: string;
  location_name: string;
  year: number;
  month: number;
  name: string;
  description: string;
  status: "draft" | "review" | "approved" | "reopened" | "archived";
  content_hash: string;
  validation_fingerprint: string;
  approved_at: string | null;
  approved_by: string | null;
  reopened_at: string | null;
  reopened_by: string | null;
  line_count: number;
  is_active: boolean;
};

export type RevenueBudgetLine = {
  id: string;
  budget_period: string;
  category: string;
  category_code: string;
  category_name: string;
  category_code_snapshot: string;
  category_name_snapshot: string;
  budget_amount: string;
  notes: string;
  display_order: number;
  is_active: boolean;
};

export type RevenueBudgetPreview = {
  period: string;
  location: string;
  location_name: string;
  location_code: string;
  year: number;
  month: number;
  status: RevenueBudgetPeriod["status"];
  content_hash: string;
  validation_fingerprint: string;
  lines: RevenueBudgetLine[];
  warnings: RevenueIssue[];
  errors: RevenueIssue[];
  issues: RevenueIssue[];
  summary: {
    budget_total: string;
    line_count: number;
    warning_count: number;
    error_count: number;
  };
  can_approve: boolean;
};

export type RevenueActualPeriod = {
  id: string;
  location: string;
  location_name: string;
  year: number;
  month: number;
  revenue_budget_period: string | null;
  labor_cost_budget_period: string | null;
  labor_cost_estimate_period: string | null;
  name: string;
  description: string;
  status: "draft" | "review" | "finalized" | "reopened" | "archived";
  content_hash: string;
  validation_fingerprint: string;
  finalized_at: string | null;
  finalized_by: string | null;
  reopened_at: string | null;
  reopened_by: string | null;
  line_count: number;
  is_active: boolean;
};

export type RevenueActualLine = {
  id: string;
  actual_period: string;
  category: string;
  category_code: string;
  category_name: string;
  category_code_snapshot: string;
  category_name_snapshot: string;
  actual_amount: string;
  source: "manual" | "imported" | "adjusted";
  notes: string;
  display_order: number;
  is_active: boolean;
};

export type RevenuePerformanceLine = {
  category: string | null;
  category_code_snapshot: string;
  category_name_snapshot: string;
  budget_amount: string;
  actual_amount: string;
  variance_amount: string;
  attainment_percent: string | null;
  warning_count: number;
  warnings: RevenueIssue[];
  error_count: number;
  errors: RevenueIssue[];
  display_order: number;
};

export type RevenuePerformance = {
  period: string | null;
  location: string;
  location_name?: string;
  location_code?: string;
  year: number;
  month: number;
  status: RevenueActualPeriod["status"] | "unavailable";
  revenue_budget_source_status: "approved" | "live" | "unavailable";
  labor_cost_budget_source_status: "approved" | "live" | "unavailable";
  labor_cost_estimate_source_status: "finalized" | "live" | "unavailable";
  revenue_budget_period: string | null;
  labor_cost_budget_period: string | null;
  labor_cost_estimate_period: string | null;
  budget_content_hash?: string;
  labor_budget_content_hash?: string;
  labor_estimate_content_hash?: string;
  content_hash: string;
  validation_fingerprint: string;
  summary: {
    revenue_budget_total: string;
    revenue_actual_total: string;
    revenue_variance_amount: string;
    revenue_attainment_percent: string | null;
    labor_budget_amount: string;
    planned_labor_cost: string;
    actual_labor_cost_estimate: string;
    budget_labor_cost_ratio: string | null;
    planned_labor_cost_ratio_to_budget_revenue: string | null;
    planned_labor_cost_ratio_to_actual_revenue: string | null;
    actual_labor_cost_ratio: string | null;
    planned_vs_labor_budget_amount: string;
    actual_vs_labor_budget_amount: string;
    actual_vs_planned_labor_cost_amount: string;
    line_count: number;
    warning_count: number;
    error_count: number;
  };
  lines?: RevenueActualLine[];
  performance_lines: RevenuePerformanceLine[];
  warnings: RevenueIssue[];
  errors: RevenueIssue[];
  issues: RevenueIssue[];
  can_finalize: boolean;
  is_snapshot?: boolean;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
