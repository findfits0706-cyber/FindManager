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

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
