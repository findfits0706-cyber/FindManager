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
