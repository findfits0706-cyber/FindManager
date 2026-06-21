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

export type Location = {
  id: string;
  code: string;
  name: string;
  short_name: string;
  timezone: string;
  is_active: boolean;
};

export type WorkArea = {
  id: string;
  location: string;
  code: string;
  name: string;
  is_active: boolean;
};

export type WorkCategory = {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
};

export type WorkType = {
  id: string;
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
  is_active: boolean;
};

export type StaffLocation = {
  id: string;
  staff: string;
  staff_display_name?: string;
  location: string;
  location_name?: string;
  is_primary: boolean;
  valid_from: string;
  valid_until: string | null;
  is_active: boolean;
};

export type StaffCapability = {
  id: string;
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
  notes: string;
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
  notes: string;
  is_active: boolean;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
