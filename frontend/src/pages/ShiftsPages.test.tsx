import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { AppShell } from "../components/AppShell";
import { AuthProvider } from "../features/auth/AuthContext";
import { addDaysToIsoDate, formatLocalIsoDate } from "../lib/localDate";
import { labelToOffset, offsetToLabel } from "../lib/timeOffsets";
import { clampSegmentToRange, durationToWidth, offsetToPosition, type TimelineRange } from "../lib/timeline";
import { chunkRowsForPrint, estimatePrintRowHeight, printSlotWidthForRange } from "../lib/timelinePrint";
import { AttendanceCorrectionRequestsPage } from "./AttendanceCorrectionRequestsPage";
import { AttendancePage } from "./AttendancePage";
import { MonthlyShiftsPage } from "./MonthlyShiftsPage";
import { MyAttendancePage } from "./MyAttendancePage";
import { MyPublishedShiftsPage } from "./MyPublishedShiftsPage";
import { MyShiftChangeRequestsPage } from "./MyShiftChangeRequestsPage";
import { MyShiftRequestsPage } from "./MyShiftRequestsPage";
import { ShiftChangeRequestsPage } from "./ShiftChangeRequestsPage";
import { ShiftTimelinePage } from "./ShiftTimelinePage";
import { ShiftPatternsPage } from "./ShiftPatternsPage";
import { ShiftRequestPeriodsPage } from "./ShiftRequestPeriodsPage";
import { WeeklyTemplatesPage } from "./WeeklyTemplatesPage";
import type { PublicationPreview, ShiftTimelineResponse } from "../lib/types";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const confirmMock = vi.spyOn(window, "confirm");
const printMock = vi.spyOn(window, "print").mockImplementation(() => undefined);

function renderWithAuth(element: ReactNode, initialEntries = ["/"]) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>{element}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockAuthAndApi(roles: string[], handlers: Record<string, unknown>) {
  fetchMock.mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/v1/auth/me/")) {
      return {
        ok: true,
        json: async () => ({
          id: "u1",
          username: "user",
          display_name: "表示ユーザー",
          employee_code: "EMP-1",
          email: "",
          employment_status: "active",
          must_change_password: false,
          roles,
          permissions: [],
        }),
      } as Response;
    }
    if (url.endsWith("/api/v1/auth/csrf/")) {
      return { ok: true, json: async () => ({ csrfToken: "token" }) } as Response;
    }
    for (const [fragment, payload] of Object.entries(handlers)) {
      if (url.includes(fragment)) {
        const resolved = typeof payload === "function" ? payload(input, init) : payload;
        if (resolved instanceof Response) return resolved;
        if (resolved && typeof resolved === "object" && "__error" in resolved) {
          return { ok: false, status: 500, json: async () => ({ detail: "API failed." }) } as Response;
        }
        return { ok: true, json: async () => resolved } as Response;
      }
    }
    return { ok: true, json: async () => ({ count: 0, next: null, previous: null, results: [] }) } as Response;
  });
}

async function findScreenTimelineButton(name: RegExp | string) {
  await waitFor(() => expect(document.querySelector(".screen-timeline")).toBeInTheDocument());
  return within(document.querySelector(".screen-timeline") as HTMLElement).findByRole("button", { name });
}

const locations = { count: 1, next: null, previous: null, results: [{ id: "l1", name: "本館", is_active: true }] };
const twoLocations = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: "l1", name: "本館", is_active: true },
    { id: "l2", name: "別館", is_active: true },
  ],
};
const workTypes = {
  count: 1,
  next: null,
  previous: null,
  results: [{ id: "w1", name: "ジム業務", short_name: "ジム", color_key: "blue", is_active: true }],
};
const workAreas = { count: 1, next: null, previous: null, results: [{ id: "a1", location: "l1", name: "ジム", is_active: true }] };
const monthlyPlan = {
  id: "m1",
  location: "l1",
  location_name: "本館",
  year: 2028,
  month: 2,
  name: "2028年2月 本館シフト",
  assignment_count: 1,
  staff_count: 1,
  source_weekly_template: null,
  last_generated_at: null,
  workflow_status: "draft" as const,
  confirmed_at: null,
  confirmed_by: null,
  confirmed_content_hash: "",
  is_editable: true,
  current_publication: null,
  publication_count: 0,
  is_active: true,
};
const confirmedMonthlyPlan = {
  ...monthlyPlan,
  workflow_status: "confirmed" as const,
  confirmed_content_hash: "hash-current",
  is_editable: false,
};
const attendanceSummary = {
  id: "ar1",
  status: "clocked_out" as const,
  source: "scheduled" as const,
  actual_start_offset_minutes: 525,
  actual_end_offset_minutes: 1005,
  break_minutes: 60,
  worked_minutes: 420,
  difference_start_minutes: 15,
  difference_end_minutes: -15,
  difference_worked_minutes: -30,
  warning_count: 1,
  warnings: [{ code: "shorter_worked", message: "予定より勤務時間が短くなっています。" }],
  confirmed_at: null,
};
function publicationPreview(overrides: Partial<PublicationPreview> = {}): PublicationPreview {
  return {
    plan: "m1",
    workflow_status: "draft",
    content_hash: "hash-current",
    confirmed_content_hash: "",
    confirmation_stale: false,
    next_publication_version: 1,
    validation_fingerprint: "fingerprint-1",
    summary: {
      assignment_count: 1,
      staff_count: 1,
      segment_count: 1,
      work_minutes: 450,
      break_minutes: 60,
      error_count: 0,
      warning_count: 1,
    },
    items: [
      {
        scope: "assignment",
        assignment: "ma1",
        work_date: "2028-02-01",
        staff: "staff1",
        staff_display_name: "スタッフA",
        pattern_short_name: "早",
        warning_count: 1,
        segment_count: 1,
        issues: [{ severity: "warning", code: "assisted_capability", message: "warning" }],
      },
    ],
    can_confirm: true,
    can_publish: false,
    ...overrides,
  };
}
function publicationPreviewWarning(code: string, message = "warning", overrides: Partial<PublicationPreview> = {}): PublicationPreview {
  return publicationPreview({
    validation_fingerprint: "server-validation-unchanged",
    items: [
      {
        scope: "assignment",
        assignment: "ma1",
        work_date: "2028-02-01",
        staff: "staff1",
        staff_display_name: "スタッフA",
        pattern_short_name: "早",
        warning_count: 1,
        segment_count: 1,
        issues: [{ severity: "warning", code, message }],
      },
    ],
    ...overrides,
  });
}
function publicationPreviewWithoutWarnings(overrides: Partial<PublicationPreview> = {}): PublicationPreview {
  return publicationPreview({
    summary: {
      assignment_count: 1,
      staff_count: 1,
      segment_count: 1,
      work_minutes: 450,
      break_minutes: 60,
      error_count: 0,
      warning_count: 0,
    },
    items: [],
    ...overrides,
  });
}
function publicationPreviewWithError(overrides: Partial<PublicationPreview> = {}): PublicationPreview {
  return publicationPreview({
    validation_fingerprint: "server-validation-error",
    summary: {
      assignment_count: 1,
      staff_count: 1,
      segment_count: 1,
      work_minutes: 450,
      break_minutes: 60,
      error_count: 1,
      warning_count: 0,
    },
    items: [
      {
        scope: "assignment",
        assignment: "ma1",
        work_date: "2028-02-01",
        staff: "staff1",
        staff_display_name: "スタッフA",
        pattern_short_name: "早",
        warning_count: 0,
        segment_count: 1,
        issues: [{ severity: "error", code: "missing_capability", message: "error" }],
      },
    ],
    can_confirm: false,
    can_publish: false,
    ...overrides,
  });
}
function fetchCallsIncluding(fragment: string) {
  return fetchMock.mock.calls.filter(([input]) => String(input).includes(fragment));
}
async function openMonthlyPublicationPreview() {
  await screen.findByRole("option", { name: "本館" });
  await userEvent.selectOptions(screen.getByLabelText("拠点"), "l1");
  await userEvent.click(await screen.findByRole("button", { name: "月間表を開く" }));
  await userEvent.click(await screen.findByRole("button", { name: "公開プレビュー" }));
}
const monthlyMatrix = {
  plan: { id: "m1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "2028年2月 本館シフト" },
  shift_change_request_summary: {
    open_count: 1,
    applied_count: 1,
    needs_republish: true,
  },
  shift_request_period: {
    id: "rp1",
    location: "l1",
    location_name: "本館",
    year: 2028,
    month: 2,
    name: "2028年2月 希望提出",
    description: "",
    opens_at: "2028-01-01T00:00:00+09:00",
    closes_at: "2028-01-31T23:59:00+09:00",
    status: "open" as const,
    draft_count: 1,
    submitted_count: 2,
    returned_count: 1,
    locked_count: 1,
    submission_count: 5,
    target_staff_count: 6,
    not_created_count: 1,
    item_count: 9,
    is_active: true,
  },
  dates: Array.from({ length: 29 }, (_, index) => {
    const date = new Date(2028, 1, index + 1);
    const weekday = (date.getDay() + 6) % 7;
    return {
      date: `2028-02-${String(index + 1).padStart(2, "0")}`,
      day: index + 1,
      weekday,
      weekday_label: ["月", "火", "水", "木", "金", "土", "日"][weekday],
      is_saturday: weekday === 5,
      is_sunday: weekday === 6,
    };
  }),
  rows: [
    {
      staff: "staff1",
      staff_display_name: "スタッフA",
      employee_code: "EMP-A",
      assignments: {
        "2028-02-01": {
          id: "ma1",
          pattern_short_name: "早",
          start_offset_minutes: 510,
          end_offset_minutes: 1020,
          source_type: "template" as const,
          is_customized: false,
          warning_count: 0,
          attendance: attendanceSummary,
          shift_change_requests: [
            {
              id: "cr1",
              request_type: "drop_shift",
              status: "submitted",
              priority: "high",
              requested_staff: "staff2",
              requested_staff_display_name: "スタッフB",
              requested_work_date: null,
              requested_start_offset_minutes: null,
              requested_end_offset_minutes: null,
              reason: "急用",
              manager_note: "",
              applied_at: null,
            },
          ],
        },
      },
      inactive_assignments: {
        "2028-02-02": { id: "old1", pattern_short_name: "遅" },
      },
    },
  ],
};
const shiftTimeline = {
  plan: { id: "m1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "2028年2月 本館シフト" },
  range: {
    date_from: "2028-02-01",
    date_to: "2028-02-01",
    day_count: 1,
    earliest_start_offset: 510,
    latest_end_offset: 1500,
    suggested_start_offset: 360,
    suggested_end_offset: 1500,
  },
  dates: [monthlyMatrix.dates[0]],
  rows: [
    {
      staff: "staff1",
      staff_display_name: "スタッフA",
      employee_code: "EMP-A",
      days: {
        "2028-02-01": {
          assignment: {
            id: "ma1",
            pattern_name: "早番",
            pattern_short_name: "早",
            source_type: "template" as const,
            is_customized: true,
            notes: "note",
            warning_count: 1,
            attendance: attendanceSummary,
          },
          segments: [
            {
              id: "seg1",
              work_type: "w1",
              work_area: "a1",
              work_type_name: "ジム業務",
              work_type_short_name: "ジム",
              work_type_color_key: "blue",
              work_type_is_break: false,
              work_area_name: "ジム",
              start_offset_minutes: 510,
              end_offset_minutes: 1020,
              duration_minutes: 510,
              display_order: 10,
              notes: "",
              lane: 0,
              lane_count: 2,
            },
            {
              id: "seg2",
              work_type: "w2",
              work_area: null,
              work_type_name: "休憩",
              work_type_short_name: "休",
              work_type_color_key: "amber",
              work_type_is_break: true,
              work_area_name: "",
              start_offset_minutes: 900,
              end_offset_minutes: 960,
              duration_minutes: 60,
              display_order: 20,
              notes: "",
              lane: 1,
              lane_count: 2,
            },
          ],
        },
      },
    },
  ],
  legend: [
    { work_type: "w1", name: "ジム業務", short_name: "ジム", color_key: "blue", is_break: false },
    { work_type: "w2", name: "休憩", short_name: "休", color_key: "amber", is_break: true },
  ],
  summary: { staff_count: 1, assignment_count: 1, segment_count: 2, work_minutes: 510, break_minutes: 60 },
};
const assignmentDetail = {
  id: "ma1",
  monthly_shift_plan: "m1",
  work_date: "2028-02-01",
  staff: "staff1",
  staff_display_name: "スタッフA",
  source_type: "template" as const,
  source_shift_pattern: "p1",
  pattern_name_snapshot: "早番",
  pattern_short_name_snapshot: "早",
  notes: "全体備考",
  is_customized: true,
  is_active: true,
  start_offset_minutes: 510,
  end_offset_minutes: 1020,
  work_minutes: 450,
  break_minutes: 60,
  segment_count: 2,
  warnings: [],
  segments: [
    {
      id: "seg1",
      work_type: "w1",
      work_area: "a1",
      work_type_name_snapshot: "ジム業務",
      work_type_short_name_snapshot: "ジム",
      work_type_color_key_snapshot: "blue",
      work_type_is_break_snapshot: false,
      work_area_name_snapshot: "ジム",
      start_offset_minutes: 510,
      end_offset_minutes: 960,
      duration_minutes: 450,
      display_order: 10,
      notes: "ジム備考",
      is_active: true,
    },
    {
      id: "seg2",
      work_type: "w2",
      work_area: null,
      work_type_name_snapshot: "休憩",
      work_type_short_name_snapshot: "休",
      work_type_color_key_snapshot: "amber",
      work_type_is_break_snapshot: true,
      work_area_name_snapshot: "",
      start_offset_minutes: 960,
      end_offset_minutes: 1020,
      duration_minutes: 60,
      display_order: 20,
      notes: "休憩備考",
      is_active: true,
    },
    {
      id: "seg3",
      work_type: "w3",
      work_area: null,
      work_type_name_snapshot: "無効",
      work_type_short_name_snapshot: "無",
      work_type_color_key_snapshot: "slate",
      work_type_is_break_snapshot: false,
      work_area_name_snapshot: "",
      start_offset_minutes: 1020,
      end_offset_minutes: 1080,
      duration_minutes: 60,
      display_order: 30,
      notes: "",
      is_active: false,
    },
  ],
};
const filteredShiftTimeline = {
  ...shiftTimeline,
  rows: [
    {
      ...shiftTimeline.rows[0],
      days: {
        "2028-02-01": {
          ...shiftTimeline.rows[0].days["2028-02-01"],
          segments: [shiftTimeline.rows[0].days["2028-02-01"].segments[0]],
        },
      },
    },
  ],
  legend: [shiftTimeline.legend[0]],
  summary: { staff_count: 1, assignment_count: 1, segment_count: 1, work_minutes: 510, break_minutes: 0 },
};
const emptyStaffTimeline = {
  ...shiftTimeline,
  rows: [
    {
      staff: "staff2",
      staff_display_name: "空スタッフ",
      employee_code: "EMP-Z",
      days: { "2028-02-01": { assignment: null, segments: [] } },
    },
  ],
  legend: [],
  summary: { staff_count: 1, assignment_count: 0, segment_count: 0, work_minutes: 0, break_minutes: 0 },
};
const emptyRowsTimeline = {
  ...shiftTimeline,
  rows: [],
  legend: [],
  summary: { staff_count: 0, assignment_count: 0, segment_count: 0, work_minutes: 0, break_minutes: 0 },
};
const weeklyPrintTimeline = {
  ...shiftTimeline,
  range: { ...shiftTimeline.range, date_to: "2028-02-07", day_count: 7 },
  dates: monthlyMatrix.dates.slice(0, 7),
  rows: Array.from({ length: 13 }, (_, index) => ({
    staff: `staff-${index + 1}`,
    staff_display_name: `印刷スタッフ${index + 1}`,
    employee_code: `EMP-P${index + 1}`,
    days: Object.fromEntries(
      monthlyMatrix.dates.slice(0, 7).map((date) => [
        date.date,
        index === 0 && date.date === "2028-02-01"
          ? shiftTimeline.rows[0].days["2028-02-01"]
          : { assignment: null, segments: [] },
      ]),
    ),
  })),
  summary: { staff_count: 13, assignment_count: 1, segment_count: 2, work_minutes: 510, break_minutes: 60 },
};
const threeLaneDay: ShiftTimelineResponse["rows"][number]["days"][string] = {
  assignment: shiftTimeline.rows[0].days["2028-02-01"].assignment,
  segments: [
    { ...shiftTimeline.rows[0].days["2028-02-01"].segments[0], id: "lane-a", start_offset_minutes: 540, end_offset_minutes: 660, lane: 0, lane_count: 3 },
    { ...shiftTimeline.rows[0].days["2028-02-01"].segments[0], id: "lane-b", start_offset_minutes: 570, end_offset_minutes: 630, lane: 1, lane_count: 3 },
    { ...shiftTimeline.rows[0].days["2028-02-01"].segments[0], id: "lane-c", start_offset_minutes: 600, end_offset_minutes: 690, lane: 2, lane_count: 3 },
  ],
};
const highLaneRows: ShiftTimelineResponse["rows"] = Array.from({ length: 13 }, (_, index) => ({
  staff: `high-${index + 1}`,
  staff_display_name: `高レーン${index + 1}`,
  employee_code: `EMP-H${index + 1}`,
  days: { "2028-02-01": threeLaneDay },
}));
const oneLaneRows: ShiftTimelineResponse["rows"] = Array.from({ length: 13 }, (_, index) => ({
  staff: `one-${index + 1}`,
  staff_display_name: `1レーン${index + 1}`,
  employee_code: `EMP-O${index + 1}`,
  days: { "2028-02-01": { assignment: null, segments: [] } },
}));
const patterns = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: "p1",
      location: "l1",
      location_name: "本館",
      code: "early",
      name: "早番",
      short_name: "早",
      description: "",
      display_order: 10,
      is_active: true,
      start_offset_minutes: 510,
      end_offset_minutes: 1020,
      total_minutes: 510,
      work_minutes: 450,
      break_minutes: 60,
      segment_count: 1,
      segments: [
        {
          id: "s1",
          work_type: "w1",
          work_type_name: "ジム業務",
          work_type_color_key: "blue",
          work_area: "a1",
          start_offset_minutes: 510,
          end_offset_minutes: 1020,
          display_order: 10,
          notes: "",
          is_active: true,
        },
      ],
    },
  ],
};

function monthlyPublicationApiHandlers(
  planResult: typeof monthlyPlan | typeof confirmedMonthlyPlan,
  previewHandler: unknown,
  extraHandlers: Record<string, unknown> = {},
) {
  return {
    "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
    "/api/v1/monthly-shift-plans/m1/publication-preview/": previewHandler,
    "/api/v1/monthly-shift-plans/m1/publications/": [],
    ...extraHandlers,
    "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [planResult] },
    "/api/v1/locations/": locations,
    "/api/v1/shift-patterns/": patterns,
    "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
    "/api/v1/work-types/": workTypes,
    "/api/v1/work-areas/": workAreas,
    "/api/v1/work-type-availabilities/": { count: 0, next: null, previous: null, results: [] },
  };
}

describe("shift settings pages", () => {
  beforeEach(() => {
    cleanup();
    fetchMock.mockReset();
    confirmMock.mockReset();
    printMock.mockClear();
  });

  it("shows shift settings menu for managers and hides it for staff", async () => {
    mockAuthAndApi(["shift_manager"], {});
    renderWithAuth(
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<div>home</div>} />
        </Route>
      </Routes>,
    );
    expect(await screen.findByRole("link", { name: "勤務パターン" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "月間シフト" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "日別・週別シフト" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "希望提出管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "希望提出" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "自分のシフト" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "週間テンプレート" })).toBeInTheDocument();
  });

  it("shows request period management and submission actions", async () => {
    mockAuthAndApi(["system_admin"], {
      "/api/v1/locations/": locations,
      "/api/v1/shift-request-periods/p1/submissions/": [
        {
          id: "sub1",
          request_period: "p1",
          period: { id: "p1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "希望", status: "open", opens_at: "2028-01-01", closes_at: "2028-01-31" },
          staff: "staff1",
          staff_display_name: "スタッフA",
          status: "submitted",
          can_edit: false,
          can_submit: false,
          submitted_at: "2028-01-10",
          returned_at: null,
          return_reason: "",
          notes: "note",
          item_count: 1,
          items: [{ id: "i1", request_type: "day_off", work_date: "2028-02-01", start_offset_minutes: null, end_offset_minutes: null, work_type: null, work_area: null, priority: "high", reason: "私用", notes: "" }],
        },
      ],
      "/api/v1/shift-request-periods/": {
        count: 1,
        next: null,
        previous: null,
        results: [
          { id: "p1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "希望", description: "", opens_at: "2028-01-01", closes_at: "2028-01-31", status: "open", draft_count: 0, submitted_count: 1, returned_count: 0, locked_count: 0, item_count: 1, is_active: true },
        ],
      },
      "/api/v1/shift-request-submissions/sub1/lock/": { status: "locked" },
    });
    renderWithAuth(<ShiftRequestPeriodsPage />);
    expect(await screen.findByText("希望提出管理")).toBeInTheDocument();
    expect(
      await screen.findByText(
        (_content, element) =>
          element?.tagName === "TD" && (element.textContent?.includes("submitted 1") ?? false),
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "提出状況" }));
    expect(await screen.findByText("スタッフA")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "詳細" }));
    expect(screen.getByText("私用")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "lock" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/shift-request-submissions/sub1/lock/"), expect.anything());
    return;
    expect(await screen.findByText("希望提出管理")).toBeInTheDocument();
    expect(
      await screen.findByText(
        (_content, element) =>
          element?.tagName === "TD" && (element.textContent?.includes("submitted 1") ?? false),
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "提出状況" }));
    expect(await screen.findByText("スタッフA")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "詳細" }));
    expect(screen.getByText("私用")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "lock" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/shift-request-submissions/sub1/lock/"), expect.anything());
  });

  it("lets users edit and submit their own shift requests without staff id", async () => {
    const submission = {
      id: "sub1",
      request_period: "p1",
      period: { id: "p1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "希望", status: "open", opens_at: "2028-01-01", closes_at: "2028-01-31" },
      staff: "u1",
      staff_display_name: "表示ユーザー",
      status: "draft",
      can_edit: true,
      can_submit: true,
      submitted_at: null,
      returned_at: null,
      return_reason: "",
      notes: "",
      items: [],
    };
    mockAuthAndApi(["staff"], {
      "/api/v1/locations/": locations,
      "/api/v1/my-shift-request-periods/p1/submission/": submission,
      "/api/v1/my-shift-request-periods/p1/submit/": { ...submission, status: "submitted", can_edit: false },
      "/api/v1/my-shift-request-periods/": [
        { id: "p1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "希望", description: "", opens_at: "2028-01-01", closes_at: "2028-01-31", status: "open", is_active: true },
      ],
    });
    renderWithAuth(<MyShiftRequestsPage />);
    expect(await screen.findByText("希望提出")).toBeInTheDocument();
    expect(await screen.findByText("未作成")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "開く" }));
    await userEvent.click(screen.getByRole("button", { name: "希望休追加" }));
    await userEvent.type(screen.getByLabelText("理由"), "遘∫畑");
    await userEvent.click(screen.getByRole("button", { name: "下書き保存" }));
    await userEvent.click(screen.getByRole("button", { name: "提出" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-shift-request-periods/p1/submit/"), expect.anything());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("staff="))).toBe(false);
    return;
    expect(await screen.findByText("希望提出")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "開く" }));
    await userEvent.click(screen.getByRole("button", { name: "希望休追加" }));
    await userEvent.type(screen.getByLabelText("理由"), "私用");
    await userEvent.click(screen.getByRole("button", { name: "下書き保存" }));
    await userEvent.click(screen.getByRole("button", { name: "提出" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-shift-request-periods/p1/submit/"), expect.anything());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("staff="))).toBe(false);
  });

  it("shows my published shifts from snapshot API", async () => {
    mockAuthAndApi(["staff"], {
      "/api/v1/my-published-shifts/": {
        range: { date_from: "2028-02-01", date_to: "2028-02-29" },
        dates: [
          {
            date: "2028-02-01",
            weekday: 1,
            weekday_label: "火",
            is_saturday: false,
            is_sunday: false,
          },
        ],
        shifts: [
          {
            id: "pub-a1",
            source_assignment: "ma1",
            work_date: "2028-02-01",
            staff: "u1",
            staff_display_name_snapshot: "表示ユーザー",
            employee_code_snapshot: "EMP-1",
            source_type: "manual",
            is_customized: false,
            pattern_code_snapshot: "early",
            pattern_name_snapshot: "早番",
            pattern_short_name_snapshot: "早",
            notes: "公開備考",
            display_order: 0,
            warning_count_snapshot: 0,
            start_offset_minutes: 510,
            end_offset_minutes: 1020,
            work_minutes: 450,
            break_minutes: 60,
            attendance: { ...attendanceSummary, status: "clocked_in" },
            shift_change_requests: [],
            segments: [
              {
                id: "pub-s1",
                source_segment: "seg1",
                work_type: "w1",
                work_area: "a1",
                work_type_name_snapshot: "ジム業務",
                work_type_short_name_snapshot: "ジム",
                work_type_color_key_snapshot: "blue",
                work_type_is_break_snapshot: false,
                work_area_name_snapshot: "ジム",
                start_offset_minutes: 510,
                end_offset_minutes: 960,
                duration_minutes: 450,
                display_order: 10,
                notes: "",
              },
            ],
            publication: {
              id: "pub1",
              version: 1,
              monthly_shift_plan: "m1",
              location: "l1",
              location_name: "本館",
              year: 2028,
              month: 2,
              published_at: "2028-01-25T00:00:00+09:00",
            },
          },
        ],
      },
    });
    renderWithAuth(<MyPublishedShiftsPage />);
    expect(await screen.findByText("自分のシフト")).toBeInTheDocument();
    expect(await screen.findByText("2028-02-01")).toBeInTheDocument();
    expect(screen.getAllByText("本館").length).toBeGreaterThan(0);
    expect(screen.getByText("08:30~17:00")).toBeInTheDocument();
    expect(screen.getByText("火")).toBeInTheDocument();
    expect(screen.getByText("出勤済み / warning 1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "退勤" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-attendance/ar1/clock-out/"), expect.anything());
    await userEvent.click(screen.getByRole("button", { name: "2028-02-01" }));
    expect(screen.getByText("公開備考")).toBeInTheDocument();
    expect(screen.getByText("勤怠状態")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "勤怠修正申請" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-attendance-corrections/"), expect.anything());
    await userEvent.type(screen.getByLabelText("理由"), "急用");
    await userEvent.click(screen.getByRole("button", { name: "提出" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-shift-change-requests/"), expect.anything());
    const changeRequestCall = fetchMock.mock.calls.find(
      ([input, init]) => String(input).includes("/api/v1/my-shift-change-requests/") && init?.method === "POST",
    );
    expect(changeRequestCall?.[1]?.body).toContain("\"publication_assignment\":\"pub-a1\"");
    expect(changeRequestCall?.[1]?.body).not.toContain("target_staff");
    expect(changeRequestCall?.[1]?.body).not.toContain("requester");
    await userEvent.clear(screen.getByLabelText("年"));
    await userEvent.type(screen.getByLabelText("年"), "2029");
    expect(screen.queryByText("公開備考")).not.toBeInTheDocument();
  });

  it("lists my attendance and creates a correction request", async () => {
    const record = {
      ...attendanceSummary,
      location: "l1",
      location_name: "本館",
      staff: "u1",
      staff_display_name: "表示ユーザー",
      employee_code: "EMP-1",
      work_date: "2028-02-01",
      monthly_shift_plan: "m1",
      monthly_shift_assignment: "ma1",
      publication: "pub1",
      publication_assignment: "pub-a1",
      scheduled_start_offset_minutes: 510,
      scheduled_end_offset_minutes: 1020,
      scheduled_pattern_name_snapshot: "早番",
      scheduled_pattern_short_name_snapshot: "早",
      actual_clock_in_at: "2028-02-01T08:45:00+09:00",
      actual_clock_out_at: "2028-02-01T16:45:00+09:00",
      manager_note: "",
      staff_note: "",
      confirmed_by: null,
      events: [
        {
          id: "ev1",
          attendance_record: "ar1",
          event_type: "clock_in",
          occurred_at: "2028-02-01T08:45:00+09:00",
          offset_minutes: 525,
          source: "self",
          actor: "u1",
          actor_display_name: "表示ユーザー",
          note: "",
          metadata: {},
          created_at: "2028-02-01T08:45:00+09:00",
        },
      ],
      correction_requests: [],
      can_clock_in: false,
      can_break_start: false,
      can_break_end: false,
      can_clock_out: false,
      can_request_correction: true,
      can_manage: false,
      created_at: "2028-02-01T08:45:00+09:00",
      updated_at: "2028-02-01T16:45:00+09:00",
      is_active: true,
    };
    mockAuthAndApi(["staff"], {
      "/api/v1/my-attendance/": { count: 1, next: null, previous: null, results: [record] },
      "/api/v1/locations/": locations,
      "/api/v1/my-attendance-corrections/": { id: "acr1", status: "submitted" },
    });
    renderWithAuth(<MyAttendancePage />);
    expect(await screen.findByText("自分の勤怠")).toBeInTheDocument();
    expect(await screen.findByText("shorter_worked")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "2028-02-01" }));
    expect(screen.getByText("打刻履歴")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("理由"), "打刻修正");
    await userEvent.click(screen.getByRole("button", { name: "提出" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-attendance-corrections/"), expect.anything());
  });

  it("shows attendance management operations only to managers", async () => {
    const record = {
      ...attendanceSummary,
      location: "l1",
      location_name: "本館",
      staff: "staff1",
      staff_display_name: "スタッフA",
      employee_code: "EMP-A",
      work_date: "2028-02-01",
      monthly_shift_plan: "m1",
      monthly_shift_assignment: "ma1",
      publication: "pub1",
      publication_assignment: "pub-a1",
      scheduled_start_offset_minutes: 510,
      scheduled_end_offset_minutes: 1020,
      scheduled_pattern_name_snapshot: "早番",
      scheduled_pattern_short_name_snapshot: "早",
      actual_clock_in_at: "2028-02-01T08:45:00+09:00",
      actual_clock_out_at: "2028-02-01T16:45:00+09:00",
      manager_note: "",
      staff_note: "",
      confirmed_by: null,
      events: [],
      correction_requests: [],
      can_clock_in: false,
      can_break_start: false,
      can_break_end: false,
      can_clock_out: false,
      can_request_correction: true,
      can_manage: true,
      created_at: "2028-02-01T08:45:00+09:00",
      updated_at: "2028-02-01T16:45:00+09:00",
      is_active: true,
    };
    mockAuthAndApi(["system_admin"], {
      "/api/v1/attendance-records/": { count: 1, next: null, previous: null, results: [record] },
      "/api/v1/locations/": locations,
      "/api/v1/staff/": { count: 1, next: null, previous: null, results: [{ id: "staff1", display_name: "スタッフA" }] },
    });
    renderWithAuth(<AttendancePage />);
    expect(await screen.findByText("勤怠管理")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "2028-02-01" }));
    expect(screen.getByText("管理操作")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "confirm" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/attendance-records/ar1/confirm/"), expect.anything());

    cleanup();
    fetchMock.mockReset();
    mockAuthAndApi(["supervisor"], {
      "/api/v1/attendance-records/": { count: 1, next: null, previous: null, results: [record] },
      "/api/v1/locations/": locations,
      "/api/v1/staff/": { count: 1, next: null, previous: null, results: [{ id: "staff1", display_name: "スタッフA" }] },
    });
    renderWithAuth(<AttendancePage />);
    await userEvent.click(await screen.findByRole("button", { name: "2028-02-01" }));
    expect(screen.getByText("閲覧のみです。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "confirm" })).not.toBeInTheDocument();
  });

  it("manages attendance correction requests and requires reject reason", async () => {
    const correction = {
      id: "acr1",
      attendance_record: "ar1",
      location: "l1",
      location_name: "本館",
      work_date: "2028-02-01",
      staff: "staff1",
      staff_display_name: "スタッフA",
      requester: "staff1",
      requester_display_name: "スタッフA",
      status: "submitted",
      requested_clock_in_at: "2028-02-01T09:00:00+09:00",
      requested_clock_out_at: "2028-02-01T17:00:00+09:00",
      requested_break_minutes: 60,
      requested_staff_note: "補足",
      reason: "打刻漏れ",
      manager_note: "",
      submitted_at: "2028-02-01T18:00:00+09:00",
      approved_at: null,
      approved_by: null,
      rejected_at: null,
      rejected_by: null,
      cancelled_at: null,
      cancelled_by: null,
      applied_at: null,
      applied_by: null,
      can_edit: false,
      can_submit: false,
      can_cancel: false,
      can_approve: true,
      can_apply: false,
      created_at: "2028-02-01T18:00:00+09:00",
      updated_at: "2028-02-01T18:00:00+09:00",
      is_active: true,
    };
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/attendance-correction-requests/": { count: 1, next: null, previous: null, results: [correction] },
      "/api/v1/locations/": locations,
      "/api/v1/staff/": { count: 1, next: null, previous: null, results: [{ id: "staff1", display_name: "スタッフA" }] },
    });
    renderWithAuth(<AttendanceCorrectionRequestsPage />);
    expect(await screen.findByText("勤怠修正申請")).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "2028-02-01" }));
    await userEvent.click(screen.getByRole("button", { name: "reject" }));
    expect(screen.getByText("却下理由を入力してください。")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("管理メモ"), "理由不足");
    await userEvent.click(screen.getByRole("button", { name: "approve" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/attendance-correction-requests/acr1/approve/"), expect.anything());
  });

  it("lists and edits my shift change requests", async () => {
    const draftRequest = {
      id: "cr1",
      location: "l1",
      location_name: "本館",
      monthly_shift_plan: "m1",
      publication: "pub1",
      publication_version: 1,
      publication_assignment: "pub-a1",
      requester: "u1",
      requester_display_name: "表示ユーザー",
      target_staff: "u1",
      target_staff_display_name: "表示ユーザー",
      requested_staff: null,
      requested_staff_display_name: "",
      request_type: "drop_shift",
      status: "draft",
      priority: "normal",
      work_date: "2028-02-01",
      original_start_offset_minutes: 510,
      original_end_offset_minutes: 1020,
      original_pattern_name_snapshot: "早番",
      original_pattern_short_name_snapshot: "早",
      requested_work_date: null,
      requested_shift_pattern: null,
      requested_shift_pattern_name: "",
      requested_start_offset_minutes: null,
      requested_end_offset_minutes: null,
      requested_notes: "",
      reason: "急用",
      manager_note: "",
      submitted_at: null,
      approved_at: null,
      rejected_at: null,
      cancelled_at: null,
      applied_at: null,
      can_edit: true,
      can_submit: true,
      can_cancel: true,
      can_approve: false,
      can_apply: false,
      created_at: "2028-01-25T00:00:00+09:00",
      updated_at: "2028-01-25T00:00:00+09:00",
      is_active: true,
    };
    mockAuthAndApi(["staff"], {
      "/api/v1/staff/": { count: 1, next: null, previous: null, results: [{ id: "u2", display_name: "スタッフB" }] },
      "/api/v1/my-shift-change-requests/": (input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PATCH") return { ...draftRequest, reason: "更新後" };
        if (String(input).includes("/submit/")) return { ...draftRequest, status: "submitted", can_edit: false, can_submit: false };
        if (String(input).includes("/cancel/")) return { ...draftRequest, status: "cancelled", can_edit: false, can_submit: false, can_cancel: false };
        return { count: 1, next: null, previous: null, results: [draftRequest] };
      },
    });
    renderWithAuth(<MyShiftChangeRequestsPage />);
    expect(await screen.findByText("シフト変更申請")).toBeInTheDocument();
    expect(await screen.findByText("drop_shift")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "詳細" }));
    expect(screen.getByDisplayValue("急用")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("理由"));
    await userEvent.type(screen.getByLabelText("理由"), "更新後");
    await userEvent.click(screen.getByRole("button", { name: "下書き保存" }));
    await userEvent.click(screen.getByRole("button", { name: "提出" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/my-shift-change-requests/cr1/submit/"), expect.anything());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("staff="))).toBe(false);
  });

  it("manages shift change requests and keeps supervisors read-only", async () => {
    const submittedRequest = {
      id: "cr-admin",
      location: "l1",
      location_name: "本館",
      monthly_shift_plan: "m1",
      publication: "pub1",
      publication_version: 1,
      publication_assignment: "pub-a1",
      requester: "u1",
      requester_display_name: "スタッフA",
      target_staff: "u1",
      target_staff_display_name: "スタッフA",
      requested_staff: null,
      requested_staff_display_name: "",
      request_type: "cover_request",
      status: "submitted",
      priority: "high",
      work_date: "2028-02-01",
      original_start_offset_minutes: 510,
      original_end_offset_minutes: 1020,
      original_pattern_name_snapshot: "早番",
      original_pattern_short_name_snapshot: "早",
      requested_work_date: null,
      requested_shift_pattern: null,
      requested_shift_pattern_name: "",
      requested_start_offset_minutes: null,
      requested_end_offset_minutes: null,
      requested_notes: "",
      reason: "代行依頼",
      manager_note: "",
      submitted_at: "2028-01-25T00:00:00+09:00",
      approved_at: null,
      rejected_at: null,
      cancelled_at: null,
      applied_at: null,
      can_edit: false,
      can_submit: false,
      can_cancel: true,
      can_approve: true,
      can_apply: false,
      created_at: "2028-01-25T00:00:00+09:00",
      updated_at: "2028-01-25T00:00:00+09:00",
      is_active: true,
    };
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/staff/": { count: 1, next: null, previous: null, results: [{ id: "u2", display_name: "スタッフB" }] },
      "/api/v1/shift-change-requests/": (input: RequestInfo | URL) => {
        if (String(input).includes("/approve/")) return { ...submittedRequest, status: "approved", can_approve: false, can_apply: true, manager_note: "承認" };
        if (String(input).includes("/apply/")) return { ...submittedRequest, status: "applied", can_approve: false, can_apply: false, manager_note: "反映" };
        return { count: 1, next: null, previous: null, results: [submittedRequest] };
      },
    });
    renderWithAuth(<ShiftChangeRequestsPage />);
    expect(await screen.findByText("シフト変更申請管理")).toBeInTheDocument();
    expect(await screen.findByText("代行依頼")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "詳細" }));
    await userEvent.selectOptions(screen.getByLabelText("代行/交換スタッフ"), "u2");
    await userEvent.type(screen.getByLabelText("管理メモ"), "承認");
    await userEvent.click(screen.getByRole("button", { name: "承認" }));
    await userEvent.click(await screen.findByRole("button", { name: "反映" }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/shift-change-requests/cr-admin/approve/"), expect.anything());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/shift-change-requests/cr-admin/apply/"), expect.anything());

    cleanup();
    mockAuthAndApi(["supervisor"], {
      "/api/v1/staff/": { count: 1, next: null, previous: null, results: [{ id: "u2", display_name: "スタッフB" }] },
      "/api/v1/shift-change-requests/": { count: 1, next: null, previous: null, results: [{ ...submittedRequest, can_approve: false, can_cancel: false }] },
    });
    renderWithAuth(<ShiftChangeRequestsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "詳細" }));
    expect(screen.getByText("閲覧のみです。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "承認" })).not.toBeInTheDocument();
  });

  it("calculates timeline positions and clamps next-day segments", () => {
    expect(offsetToPosition(540, 360, 12)).toBe(144);
    expect(durationToWidth(60, 12)).toBe(48);
    expect(clampSegmentToRange({ start_offset_minutes: 300, end_offset_minutes: 1500 }, { start: 360, end: 1440 })).toEqual({
      start: 360,
      end: 1440,
      duration: 1080,
      continuesLeft: true,
      continuesRight: true,
      isVisible: true,
    });
    expect(clampSegmentToRange({ start_offset_minutes: 1440, end_offset_minutes: 2880 }, { start: 0, end: 2880 }).duration).toBe(1440);
  });

  it("adds local ISO dates without toISOString drift", () => {
    expect(addDaysToIsoDate("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDaysToIsoDate("2028-02-29", 1)).toBe("2028-03-01");
    expect(addDaysToIsoDate("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDaysToIsoDate("2026-07-01", -1)).toBe("2026-06-30");
    expect(formatLocalIsoDate(new Date(2028, 1, 29))).toBe("2028-02-29");
    expect(formatLocalIsoDate(new Date(2026, 11, 31))).toBe("2026-12-31");
    const toIsoSpy = vi.spyOn(Date.prototype, "toISOString").mockImplementation(() => {
      throw new Error("toISOString should not be used");
    });
    expect(formatLocalIsoDate(new Date(2026, 6, 1, 0, 30))).toBe("2026-07-01");
    toIsoSpy.mockRestore();
    expect(addDaysToIsoDate.toString()).not.toContain("toISOString");
    expect(formatLocalIsoDate.toString()).not.toContain("toISOString");
  });

  it("converts all 15 minute offsets including 2880", () => {
    expect(offsetToLabel(510)).toBe("08:30");
    expect(offsetToLabel(1470)).toBe("翌00:30");
    expect(offsetToLabel(2880)).toBe("翌24:00");
    expect(labelToOffset("翌24:00")).toBe(2880);
    for (let value = 0; value <= 2880; value += 15) {
      expect(labelToOffset(offsetToLabel(value))).toBe(value);
    }
  });

  it("adds and removes segments and uses 15 minute options", async () => {
    mockAuthAndApi(["system_admin"], {
      "/api/v1/shift-patterns/": { ...patterns, results: [] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftPatternsPage />);
    await screen.findAllByRole("option", { name: "本館" });
    await userEvent.selectOptions((await screen.findAllByLabelText("拠点"))[1], "l1");
    await userEvent.click(await screen.findByRole("button", { name: "追加" }));
    expect(screen.getAllByRole("option", { name: "08:30" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "翌02:00" }).length).toBeGreaterThan(0);
    expect(screen.getByText(/未選択/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "削除" }));
    expect(screen.queryByText(/未選択/)).not.toBeInTheDocument();
  });

  it("cancels deactivate and confirms reactivate", async () => {
    confirmMock.mockReturnValueOnce(false).mockReturnValueOnce(true);
    mockAuthAndApi(["system_admin"], {
      "/api/v1/shift-patterns/": { ...patterns, results: [{ ...patterns.results[0], is_active: false }] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftPatternsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "再有効化" }));
    expect(confirmMock).toHaveBeenCalled();
  });

  it("prevents duplicate save submissions while saving", async () => {
    let postCount = 0;
    mockAuthAndApi(["system_admin"], {
      "/api/v1/shift-patterns/": (_input: unknown, init?: RequestInit) => {
        if (init?.method === "POST") {
          postCount += 1;
          return new Promise(() => undefined);
        }
        return { ...patterns, results: [] };
      },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftPatternsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "保存" }));
    await userEvent.click(await screen.findByRole("button", { name: "保存中..." }));
    expect(postCount).toBe(1);
  });

  it("hides edit controls for supervisors and redirects staff", async () => {
    mockAuthAndApi(["supervisor"], {
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftPatternsPage />);
    expect(await screen.findByRole("button", { name: "詳細" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();

    fetchMock.mockReset();
    mockAuthAndApi(["staff"], {});
    renderWithAuth(
      <Routes>
        <Route path="/" element={<ShiftPatternsPage />} />
        <Route path="/403" element={<div>Forbidden</div>} />
      </Routes>,
    );
    expect(await screen.findByText("Forbidden")).toBeInTheDocument();
  });

  it("shows only selected location patterns in weekly grid and prevents duplicate staff rows", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": {
        count: 2,
        next: null,
        previous: null,
        results: [...patterns.results, { ...patterns.results[0], id: "p2", location: "other", short_name: "他" }],
      },
      "/api/v1/staff-locations/": {
        count: 1,
        next: null,
        previous: null,
        results: [{ id: "sl1", staff: "staff1", staff_display_name: "スタッフA", location: "l1", is_active: true }],
      },
    });
    renderWithAuth(<WeeklyTemplatesPage />);
    await screen.findAllByRole("option", { name: "本館" });
    await userEvent.selectOptions((await screen.findAllByLabelText("拠点"))[1], "l1");
    await screen.findByRole("option", { name: "スタッフA" });
    await userEvent.selectOptions(await screen.findByLabelText("スタッフ追加"), "staff1");
    expect(screen.getByText("スタッフA")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("スタッフ検索"), "zz");
    expect(screen.getByText("スタッフA")).toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: "早" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("option", { name: "他" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "スタッフA" })).not.toBeInTheDocument();
  });

  it("keeps existing weekly staff names when search results exclude them", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/weekly-shift-templates/": (input: unknown) => {
        const url = String(input);
        if (url.includes("/api/v1/weekly-shift-templates/t1/")) {
          return {
            id: "t1",
            location: "l1",
            location_name: "本館",
            code: "week",
            name: "標準週",
            description: "",
            display_order: 10,
            is_active: true,
            staff_count: 1,
            entry_count: 1,
            entries: [
              {
                id: "e1",
                weekday: 0,
                staff: "staff2",
                staff_display_name: "既存スタッフ",
                shift_pattern: "p1",
                notes: "",
                display_order: 10,
                is_active: true,
              },
            ],
          };
        }
        return {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "t1",
              location: "l1",
              location_name: "本館",
              code: "week",
              name: "標準週",
              staff_count: 1,
              entry_count: 1,
              is_active: true,
            },
          ],
        };
      },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/staff-locations/": { count: 0, next: null, previous: null, results: [] },
    });
    renderWithAuth(<WeeklyTemplatesPage />);
    await userEvent.click(await screen.findByRole("button", { name: "編集" }));
    expect(await screen.findByText("既存スタッフ")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("スタッフ検索"), "別");
    expect(screen.getByText("既存スタッフ")).toBeInTheDocument();
  });

  it("shows monthly matrix, opens cells, and blocks strict preview errors", async () => {
    mockAuthAndApi(["system_admin"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-plans/m1/preview-template-generation/": {
        summary: {
          candidate_count: 1,
          create_count: 1,
          replace_count: 0,
          skip_existing_count: 0,
          skip_manual_count: 0,
          skip_invalid_count: 1,
          error_count: 1,
          warning_count: 0,
        },
        items: [
          {
            work_date: "2028-02-01",
            staff: "staff1",
            staff_display_name: "スタッフA",
            shift_pattern: "p1",
            shift_pattern_short_name: "早",
            action: "create",
            issues: [{ severity: "error", code: "missing_capability", message: "能力がありません。" }],
          },
        ],
      },
      "/api/v1/monthly-shift-assignments/ma1/": {
        id: "ma1",
        monthly_shift_plan: "m1",
        work_date: "2028-02-01",
        staff: "staff1",
        staff_display_name: "スタッフA",
        source_type: "template" as const,
        source_shift_pattern: "p1",
        pattern_name_snapshot: "早番",
        pattern_short_name_snapshot: "早",
        notes: "",
        is_customized: false,
        is_active: true,
        start_offset_minutes: 510,
        end_offset_minutes: 1020,
        work_minutes: 450,
        break_minutes: 60,
        segment_count: 1,
        warnings: [],
        segments: [],
      },
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-type-availabilities/": { count: 1, next: null, previous: null, results: [{ id: "av1", work_type: "w1", location: "l1", work_area: null, is_active: true }] },
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/weekly-shift-templates/": {
        count: 1,
        next: null,
        previous: null,
        results: [{ id: "t1", location: "l1", name: "標準週", is_active: true }],
      },
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<MonthlyShiftsPage />);
    await screen.findByRole("option", { name: "本館" });
    await userEvent.selectOptions(await screen.findByLabelText("拠点"), "l1");
    await userEvent.clear(screen.getByLabelText("年"));
    await userEvent.type(screen.getByLabelText("年"), "2028");
    await userEvent.clear(screen.getByLabelText("月"));
    await userEvent.type(screen.getByLabelText("月"), "2");
    await userEvent.click(await screen.findByRole("button", { name: "月間表を開く" }));
    expect(await screen.findByText("スタッフA")).toBeInTheDocument();
    expect(screen.getByText("変更反映済み")).toBeInTheDocument();
    expect(document.body.textContent).toContain("29");
    await userEvent.click(screen.getByText("早"));
    expect(await screen.findByText("2028-02-01")).toBeInTheDocument();
    expect(screen.getByText("drop_shift / submitted / 急用")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("週間テンプレート"), "t1");
    await userEvent.click(screen.getByRole("button", { name: "生成プレビュー" }));
    expect(await screen.findByText(/エラー 1/)).toBeInTheDocument();
    expect(screen.getByText(/検証エラースキップ 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "テンプレート適用" })).toBeDisabled();
  });

  it("opens monthly deep links after the matrix loads and supports empty cells", async () => {
    mockAuthAndApi(["system_admin"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-assignments/ma1/": assignmentDetail,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
      "/api/v1/work-type-availabilities/": {
        count: 1,
        next: null,
        previous: null,
        results: [{ id: "av1", work_type: "w1", location: "l1", work_area: null, is_active: true }],
      },
    });
    renderWithAuth(<MonthlyShiftsPage />, ["/shifts/monthly?location=l1&year=2028&month=2&date=2028-02-01&staff=staff1"]);
    expect(await screen.findByText("2028-02-01")).toBeInTheDocument();
    expect(screen.getByLabelText("勤務パターン")).toHaveValue("p1");
    expect(screen.getByDisplayValue("全体備考")).toBeInTheDocument();
    expect(screen.getByDisplayValue("ジム備考")).toBeInTheDocument();
    expect(screen.getByDisplayValue("休憩備考")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("無効")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/monthly-shift-assignments/ma1/"), expect.anything());

    cleanup();
    fetchMock.mockReset();
    mockAuthAndApi(["system_admin"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
      "/api/v1/work-type-availabilities/": { count: 0, next: null, previous: null, results: [] },
    });
    renderWithAuth(<MonthlyShiftsPage />, ["/shifts/monthly?location=l1&year=2028&month=2&date=2028-02-03&staff=staff1"]);
    expect(await screen.findByText("2028-02-03")).toBeInTheDocument();
    expect(screen.getAllByLabelText("勤務パターン").at(-1)).toHaveValue("");
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining("/api/v1/monthly-shift-assignments/ma1/"), expect.anything());
  });

  it("shows daily and weekly timelines, filters, opens detail, and prints", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": shiftTimeline,
      "/api/v1/monthly-shift-assignments/ma1/": assignmentDetail,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    expect(await screen.findByText("日別・週別シフト")).toBeInTheDocument();
    expect(document.querySelector(".screen-timeline")).toBeInTheDocument();
    expect(await findScreenTimelineButton(/ジム業務/)).toBeInTheDocument();
    expect(document.querySelector(".print-timeline")).toBeInTheDocument();
    expect(screen.getAllByText(/休憩/).length).toBeGreaterThan(0);
    await userEvent.click(await findScreenTimelineButton(/ジム業務/));
    expect(await screen.findByLabelText("勤務詳細")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "月間シフトで編集" })).toHaveAttribute(
      "href",
      "/shifts/monthly?location=l1&year=2028&month=2&date=2028-02-01&staff=staff1",
    );
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByLabelText("勤務詳細")).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("表示"), "week");
    expect(await screen.findByText("1日（火）")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("スタッフ検索"), "EMP");
    await userEvent.selectOptions(screen.getByLabelText("WorkType"), "w1");
    await userEvent.selectOptions(screen.getByLabelText("WorkArea"), "a1");
    await userEvent.click(screen.getByLabelText("休憩を表示"));
    await userEvent.selectOptions(screen.getByLabelText("表示時間範囲"), "next");
    await userEvent.selectOptions(screen.getByLabelText("表示倍率"), "拡大");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("staff_search=EMP"), expect.anything());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("work_type=w1"), expect.anything());
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("include_breaks=false"), expect.anything());
    await userEvent.click(screen.getByRole("button", { name: "印刷" }));
    await waitFor(() => expect(printMock).toHaveBeenCalled());
    expect(document.body.textContent).toMatch(/印刷日時：\d{4}年/);
  });

  it("shows full assignment detail even when the timeline is filtered", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": filteredShiftTimeline,
      "/api/v1/monthly-shift-assignments/ma1/": assignmentDetail,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    expect(await findScreenTimelineButton(/ジム業務/)).toBeInTheDocument();
    expect(within(document.querySelector(".screen-timeline") as HTMLElement).queryByRole("button", { name: /休憩/ })).not.toBeInTheDocument();
    await userEvent.click(await findScreenTimelineButton(/ジム業務/));
    expect(await screen.findByText("休憩備考")).toBeInTheDocument();
    expect(screen.getByText("1件")).toBeInTheDocument();
    expect(screen.getByText("全体備考")).toBeInTheDocument();
    expect(screen.getByText("60分")).toBeInTheDocument();
    expect(screen.queryByText("無効")).not.toBeInTheDocument();
  });

  it("keeps assigned_only=false empty staff rows visible and clears detail on filter changes", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": (input: RequestInfo | URL) =>
        String(input).includes("assigned_only=false") ? emptyStaffTimeline : shiftTimeline,
      "/api/v1/monthly-shift-assignments/ma1/": assignmentDetail,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": twoLocations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    await userEvent.click(await findScreenTimelineButton(/ジム業務/));
    expect(await screen.findByLabelText("勤務詳細")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("スタッフ検索"), "A");
    await waitFor(() => expect(screen.queryByLabelText("勤務詳細")).not.toBeInTheDocument());

    await userEvent.clear(screen.getByLabelText("スタッフ検索"));
    await userEvent.click(screen.getByLabelText("勤務ありのみ"));
    expect(await within(document.querySelector(".screen-timeline") as HTMLElement).findByText("空スタッフ")).toBeInTheDocument();
    expect(screen.queryByText("表示できるスタッフがいません。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "印刷" })).not.toBeDisabled();

    await userEvent.selectOptions(screen.getByLabelText("WorkType"), "w1");
    await userEvent.selectOptions(screen.getByLabelText("WorkArea"), "a1");
    await userEvent.selectOptions(screen.getByLabelText("拠点"), "l2");
    expect(screen.getByLabelText("WorkType")).toHaveValue("");
    expect(screen.getByLabelText("WorkArea")).toHaveValue("");
  });

  it("renders weekly print pages with headers and bounded next-day width", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": weeklyPrintTimeline,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    await findScreenTimelineButton(/ジム業務/);
    await userEvent.selectOptions(screen.getByLabelText("表示"), "week");
    expect(await screen.findByText("2日（水）")).toBeInTheDocument();
    const pages = Array.from(document.querySelectorAll("[data-testid='print-page']"));
    expect(pages).toHaveLength(14);
    expect(pages.every((page) => page.querySelector(".timeline-header"))).toBe(true);
    expect(document.querySelector(".print-timeline")?.textContent).toContain("2028-02-02（水）");
    expect(pages.at(-1)).toHaveClass("print-page-last");
    expect(pages.slice(0, -1).every((page) => !page.classList.contains("print-page-last"))).toBe(true);
    expect(printSlotWidthForRange({ start: 0, end: 2880 } satisfies TimelineRange)).toBeLessThanOrEqual(4.17);
    expect(printSlotWidthForRange({ start: 0, end: 2880 } satisfies TimelineRange)).toBeGreaterThanOrEqual(3);
    expect(document.querySelector(".timeline-layout .print-timeline")).toBeInTheDocument();
    expect(document.querySelector(".print-title")).toBeInTheDocument();
  });

  it("chunks print rows by estimated lane height and keeps staff order per date", () => {
    const oneLaneChunks = chunkRowsForPrint(oneLaneRows, "2028-02-01");
    const highLaneChunks = chunkRowsForPrint(highLaneRows, "2028-02-01");
    expect(oneLaneChunks.map((chunk) => chunk.length)).toEqual([12, 1]);
    expect(highLaneChunks[0].length).toBeLessThan(oneLaneChunks[0].length);
    expect(estimatePrintRowHeight(highLaneRows[0], "2028-02-01")).toBe(96);
    expect(highLaneChunks.flat().map((row) => row.staff)).toEqual(highLaneRows.map((row) => row.staff));

    const weekRows = weeklyPrintTimeline.rows;
    const firstDateChunks = chunkRowsForPrint(weekRows, "2028-02-01");
    const secondDateChunks = chunkRowsForPrint(weekRows, "2028-02-02");
    expect(firstDateChunks.flat().map((row) => row.staff)).toEqual(weekRows.map((row) => row.staff));
    expect(secondDateChunks.flat().map((row) => row.staff)).toEqual(weekRows.map((row) => row.staff));
    expect(firstDateChunks).not.toBe(secondDateChunks);
  });

  it("disables print for zero rows but allows staff rows without assignments", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": emptyRowsTimeline,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    expect(await screen.findByText("表示できるスタッフがいません。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "印刷" })).toBeDisabled();

    cleanup();
    fetchMock.mockReset();
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": emptyStaffTimeline,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    expect((await screen.findAllByText("空スタッフ")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "印刷" })).not.toBeDisabled();
  });

  it("shows API-specific timeline errors without masking plan failures", async () => {
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/": { __error: true },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    expect(await screen.findByText("Plan APIの取得に失敗しました。")).toBeInTheDocument();
    expect(screen.queryByText("対象月の月間シフトがありません。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "印刷" })).toBeDisabled();

    cleanup();
    fetchMock.mockReset();
    mockAuthAndApi(["shift_manager"], { "/api/v1/locations/": { __error: true } });
    renderWithAuth(<ShiftTimelinePage />);
    expect(await screen.findByText("Location APIの取得に失敗しました。")).toBeInTheDocument();

    cleanup();
    fetchMock.mockReset();
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": { __error: true },
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": { __error: true },
      "/api/v1/work-areas/": { __error: true },
    });
    renderWithAuth(<ShiftTimelinePage />);
    expect(await screen.findByText("Timeline APIの取得に失敗しました。")).toBeInTheDocument();
    expect(screen.getByText("WorkType APIの取得に失敗しました。")).toBeInTheDocument();
    expect(screen.getByText("WorkArea APIの取得に失敗しました。")).toBeInTheDocument();

    cleanup();
    fetchMock.mockReset();
    mockAuthAndApi(["shift_manager"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": shiftTimeline,
      "/api/v1/monthly-shift-assignments/ma1/": { __error: true },
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    await userEvent.click(await findScreenTimelineButton(/ジム業務/));
    expect((await screen.findAllByText("Assignment詳細APIの取得に失敗しました。")).length).toBeGreaterThan(0);
  });

  it("keeps timeline read-only for supervisors and redirects staff", async () => {
    mockAuthAndApi(["supervisor"], {
      "/api/v1/monthly-shift-plans/m1/timeline/": shiftTimeline,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
    });
    renderWithAuth(<ShiftTimelinePage />);
    await userEvent.click(await findScreenTimelineButton(/ジム業務/));
    expect(screen.queryByRole("link", { name: "月間シフトで編集" })).not.toBeInTheDocument();

    fetchMock.mockReset();
    mockAuthAndApi(["staff"], {});
    renderWithAuth(
      <Routes>
        <Route path="/" element={<ShiftTimelinePage />} />
        <Route path="/403" element={<div>Forbidden</div>} />
      </Routes>,
    );
    expect(await screen.findByText("Forbidden")).toBeInTheDocument();
  });

  it("fetches pattern detail, previews segments, moves rows, and reactivates inactive assignments", async () => {
    confirmMock.mockReturnValue(true);
    const patternDetail = {
      ...patterns.results[0],
      segments: [
        patterns.results[0].segments[0],
        { ...patterns.results[0].segments[0], id: "s2", start_offset_minutes: 1020, end_offset_minutes: 1080, display_order: 20 },
      ],
    };
    mockAuthAndApi(["system_admin"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-assignments/old1/reactivate/": {
        id: "old1",
        monthly_shift_plan: "m1",
        work_date: "2028-02-02",
        staff: "staff1",
        staff_display_name: "スタッフA",
        source_type: "manual" as const,
        source_shift_pattern: "p1",
        pattern_name_snapshot: "早番",
        pattern_short_name_snapshot: "早",
        notes: "",
        is_customized: false,
        is_active: true,
        start_offset_minutes: 510,
        end_offset_minutes: 1020,
        work_minutes: 450,
        break_minutes: 60,
        segment_count: 1,
        warnings: [{ severity: "warning", code: "assisted_capability", message: "warning" }],
        segments: [],
      },
      "/api/v1/shift-patterns/p1/": patternDetail,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
      "/api/v1/work-type-availabilities/": { count: 1, next: null, previous: null, results: [{ id: "av1", work_type: "w1", location: "l1", work_area: null, is_active: true }] },
    });
    renderWithAuth(<MonthlyShiftsPage />);
    await screen.findByRole("option", { name: "本館" });
    await userEvent.selectOptions(screen.getByLabelText("拠点"), "l1");
    await userEvent.clear(screen.getByLabelText("年"));
    await userEvent.type(screen.getByLabelText("年"), "2028");
    await userEvent.clear(screen.getByLabelText("月"));
    await userEvent.type(screen.getByLabelText("月"), "2");
    await userEvent.click(await screen.findByRole("button", { name: "月間表を開く" }));
    await screen.findAllByText("+");
    await userEvent.click(screen.getAllByText("+")[0]);
    await userEvent.selectOptions(screen.getByLabelText("勤務パターン"), "p1");
    expect(await screen.findByText(/選択パターン: 2/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/v1/shift-patterns/p1/"), expect.anything());
    expect(screen.getAllByRole("button", { name: "↑" })[0]).toBeDisabled();
    await userEvent.click(screen.getAllByRole("button", { name: "↓" })[0]);
    await userEvent.click(screen.getByText(/解除済み/));
    await userEvent.click(await screen.findByRole("button", { name: "再有効化" }));
    expect(await screen.findByText("warning")).toBeInTheDocument();
  });

  it("requires rechecking warnings when confirm warning fingerprint changes", async () => {
    let previewCalls = 0;
    mockAuthAndApi(["system_admin"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-plans/m1/publication-preview/": () => {
        previewCalls += 1;
        return publicationPreviewWarning(previewCalls === 1 ? "assisted_capability" : "trainee_capability");
      },
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
      "/api/v1/work-type-availabilities/": { count: 0, next: null, previous: null, results: [] },
    });
    renderWithAuth(<MonthlyShiftsPage />);
    await screen.findByRole("option", { name: "本館" });
    await userEvent.selectOptions(screen.getByLabelText("拠点"), "l1");
    await userEvent.click(await screen.findByRole("button", { name: "月間表を開く" }));
    await userEvent.click(await screen.findByRole("button", { name: "公開プレビュー" }));
    await userEvent.click(await screen.findByLabelText("警告内容を確認しました。"));
    await userEvent.click(screen.getByRole("button", { name: "確定" }));
    expect(await screen.findByText("警告内容が更新されました。最新の警告を確認して、再度チェックしてください。")).toBeInTheDocument();
    expect(screen.getByLabelText("警告内容を確認しました。")).not.toBeChecked();
    expect(fetchCallsIncluding("/confirm/")).toHaveLength(0);
  });

  it("does not publish when latest preview warning fingerprint changes with same warning count", async () => {
    let previewCalls = 0;
    mockAuthAndApi(["system_admin"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-plans/m1/publication-preview/": () => {
        previewCalls += 1;
        return publicationPreviewWarning(previewCalls === 1 ? "assisted_capability" : "trainee_capability", "warning", {
          workflow_status: "confirmed",
          confirmed_content_hash: "hash-current",
          can_confirm: false,
          can_publish: true,
        });
      },
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [confirmedMonthlyPlan] },
      "/api/v1/locations/": locations,
      "/api/v1/shift-patterns/": patterns,
      "/api/v1/weekly-shift-templates/": { count: 0, next: null, previous: null, results: [] },
      "/api/v1/work-types/": workTypes,
      "/api/v1/work-areas/": workAreas,
      "/api/v1/work-type-availabilities/": { count: 0, next: null, previous: null, results: [] },
    });
    renderWithAuth(<MonthlyShiftsPage />);
    await screen.findByRole("option", { name: "本館" });
    await userEvent.selectOptions(screen.getByLabelText("拠点"), "l1");
    await userEvent.click(await screen.findByRole("button", { name: "月間表を開く" }));
    await userEvent.click(await screen.findByRole("button", { name: "公開プレビュー" }));
    await userEvent.click(await screen.findByLabelText("警告内容を確認しました。"));
    await userEvent.click(screen.getByRole("button", { name: "公開" }));
    expect(await screen.findByText("警告内容が更新されました。最新の警告を確認して、再度チェックしてください。")).toBeInTheDocument();
    expect(screen.getByLabelText("警告内容を確認しました。")).not.toBeChecked();
    expect(fetchCallsIncluding("/publish/")).toHaveLength(0);
  });

  it("blocks confirm when acknowledged warnings are updated by the latest preview", async () => {
    let previewCalls = 0;
    mockAuthAndApi(
      ["system_admin"],
      monthlyPublicationApiHandlers(monthlyPlan, () => {
        previewCalls += 1;
        return publicationPreviewWarning(previewCalls === 1 ? "assisted_capability" : "trainee_capability");
      }),
    );
    renderWithAuth(<MonthlyShiftsPage />);
    await openMonthlyPublicationPreview();
    await userEvent.click(await screen.findByLabelText("警告内容を確認しました。"));
    expect(screen.getByLabelText("警告内容を確認しました。")).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "確定" }));
    expect(await screen.findByText("警告内容が更新されました。最新の警告を確認して、再度チェックしてください。")).toBeInTheDocument();
    expect(screen.getByLabelText("警告内容を確認しました。")).not.toBeChecked();
    expect(fetchCallsIncluding("/confirm/")).toHaveLength(0);
    expect(previewCalls).toBe(2);
  });

  it("blocks publish when displayed warnings are updated by the latest preview", async () => {
    let previewCalls = 0;
    mockAuthAndApi(
      ["system_admin"],
      monthlyPublicationApiHandlers(confirmedMonthlyPlan, () => {
        previewCalls += 1;
        return publicationPreviewWarning(previewCalls === 1 ? "assisted_capability" : "trainee_capability", "warning", {
          workflow_status: "confirmed",
          confirmed_content_hash: "hash-current",
          can_confirm: false,
          can_publish: true,
        });
      }),
    );
    renderWithAuth(<MonthlyShiftsPage />);
    await openMonthlyPublicationPreview();
    await userEvent.click(await screen.findByLabelText("警告内容を確認しました。"));
    expect(screen.getByLabelText("警告内容を確認しました。")).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "公開" }));
    expect(await screen.findByText("警告内容が更新されました。最新の警告を確認して、再度チェックしてください。")).toBeInTheDocument();
    expect(screen.getByLabelText("警告内容を確認しました。")).not.toBeChecked();
    expect(fetchCallsIncluding("/publish/")).toHaveLength(0);
    expect(previewCalls).toBe(2);
  });

  it("confirms exactly once after the latest preview has the same warnings", async () => {
    let previewCalls = 0;
    const warningA = {
      scope: "assignment",
      assignment: "ma1",
      work_date: "2028-02-01",
      staff: "staff1",
      staff_display_name: "スタッフA",
      pattern_short_name: "早",
      warning_count: 1,
      segment_count: 1,
      issues: [{ severity: "warning" as const, code: "assisted_capability", message: "warning A" }],
    };
    const warningB = {
      scope: "assignment",
      assignment: "ma2",
      work_date: "2028-02-02",
      staff: "staff2",
      staff_display_name: "スタッフB",
      pattern_short_name: "遅",
      warning_count: 1,
      segment_count: 1,
      issues: [{ severity: "warning" as const, code: "trainee_capability", message: "warning B" }],
    };
    mockAuthAndApi(
      ["system_admin"],
      monthlyPublicationApiHandlers(
        monthlyPlan,
        () => {
          previewCalls += 1;
          return publicationPreview({
            validation_fingerprint: previewCalls === 1 ? "server-validation-1" : "server-validation-2",
            summary: {
              assignment_count: 2,
              staff_count: 2,
              segment_count: 2,
              work_minutes: 900,
              break_minutes: 120,
              error_count: 0,
              warning_count: 2,
            },
            items: previewCalls === 1 ? [warningA, warningB] : [warningB, warningA],
          });
        },
        {
          "/api/v1/monthly-shift-plans/m1/confirm/": {
            plan: confirmedMonthlyPlan,
            preview: publicationPreviewWithoutWarnings({
              workflow_status: "confirmed",
              confirmed_content_hash: "hash-current",
              can_confirm: false,
              can_publish: true,
            }),
          },
        },
      ),
    );
    renderWithAuth(<MonthlyShiftsPage />);
    await openMonthlyPublicationPreview();
    await userEvent.click(await screen.findByLabelText("警告内容を確認しました。"));
    await userEvent.click(screen.getByRole("button", { name: "確定" }));
    await waitFor(() => expect(fetchCallsIncluding("/confirm/")).toHaveLength(1));
    expect(previewCalls).toBe(2);
  });

  it("does not confirm when the latest preview has errors", async () => {
    let previewCalls = 0;
    mockAuthAndApi(
      ["system_admin"],
      monthlyPublicationApiHandlers(monthlyPlan, () => {
        previewCalls += 1;
        return previewCalls === 1 ? publicationPreviewWithoutWarnings() : publicationPreviewWithError();
      }),
    );
    renderWithAuth(<MonthlyShiftsPage />);
    await openMonthlyPublicationPreview();
    await userEvent.click(screen.getByRole("button", { name: "確定" }));
    expect(await screen.findByText("公開プレビューにエラーがあります。エラーを解消してから確定してください。")).toBeInTheDocument();
    expect(fetchCallsIncluding("/confirm/")).toHaveLength(0);
  });

  it("does not publish when the latest preview has errors", async () => {
    let previewCalls = 0;
    mockAuthAndApi(
      ["system_admin"],
      monthlyPublicationApiHandlers(confirmedMonthlyPlan, () => {
        previewCalls += 1;
        return previewCalls === 1
          ? publicationPreviewWithoutWarnings({
              workflow_status: "confirmed",
              confirmed_content_hash: "hash-current",
              can_confirm: false,
              can_publish: true,
            })
          : publicationPreviewWithError({
              workflow_status: "confirmed",
              confirmed_content_hash: "hash-current",
            });
      }),
    );
    renderWithAuth(<MonthlyShiftsPage />);
    await openMonthlyPublicationPreview();
    await userEvent.click(screen.getByRole("button", { name: "公開" }));
    expect(await screen.findByText("公開プレビューにエラーがあります。エラーを解消してから公開してください。")).toBeInTheDocument();
    expect(fetchCallsIncluding("/publish/")).toHaveLength(0);
  });

  it("does not publish when the latest preview is confirmation stale", async () => {
    let previewCalls = 0;
    mockAuthAndApi(
      ["system_admin"],
      monthlyPublicationApiHandlers(confirmedMonthlyPlan, () => {
        previewCalls += 1;
        return publicationPreviewWithoutWarnings({
          workflow_status: "confirmed",
          content_hash: previewCalls === 1 ? "hash-current" : "hash-updated",
          confirmed_content_hash: "hash-current",
          confirmation_stale: previewCalls > 1,
          can_confirm: false,
          can_publish: previewCalls === 1,
        });
      }),
    );
    renderWithAuth(<MonthlyShiftsPage />);
    await openMonthlyPublicationPreview();
    await userEvent.click(screen.getByRole("button", { name: "公開" }));
    expect((await screen.findAllByText("確定後にシフト内容が変更されています。確定解除して再度確定してください。")).length).toBeGreaterThan(0);
    expect(fetchCallsIncluding("/publish/")).toHaveLength(0);
  });

  it("keeps supervisor monthly UI read only", async () => {
    mockAuthAndApi(["supervisor"], {
      "/api/v1/monthly-shift-plans/m1/matrix/": monthlyMatrix,
      "/api/v1/monthly-shift-plans/": { count: 1, next: null, previous: null, results: [monthlyPlan] },
      "/api/v1/locations/": locations,
    });
    renderWithAuth(<MonthlyShiftsPage />);
    await screen.findByRole("option", { name: "本館" });
    await userEvent.selectOptions(screen.getByLabelText("拠点"), "l1");
    await userEvent.click(await screen.findByRole("button", { name: "月間表を開く" }));
    expect(await screen.findByText("スタッフA")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "生成プレビュー" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存" })).not.toBeInTheDocument();
  });

  it("redirects staff away from monthly shifts", async () => {
    mockAuthAndApi(["staff"], {});
    renderWithAuth(
      <Routes>
        <Route path="/" element={<MonthlyShiftsPage />} />
        <Route path="/403" element={<div>Forbidden</div>} />
      </Routes>,
    );
    expect(await screen.findByText("Forbidden")).toBeInTheDocument();
  });
});
