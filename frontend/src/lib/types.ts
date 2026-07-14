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

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
