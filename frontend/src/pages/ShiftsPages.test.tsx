import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { AppShell } from "../components/AppShell";
import { AuthProvider } from "../features/auth/AuthContext";
import { addDaysToIsoDate } from "../lib/localDate";
import { labelToOffset, offsetToLabel } from "../lib/timeOffsets";
import { clampSegmentToRange, durationToWidth, offsetToPosition, type TimelineRange } from "../lib/timeline";
import { chunkRowsForPrint, estimatePrintRowHeight, printSlotWidthForRange } from "../lib/timelinePrint";
import { MonthlyShiftsPage } from "./MonthlyShiftsPage";
import { MyPublishedShiftsPage } from "./MyPublishedShiftsPage";
import { ShiftTimelinePage } from "./ShiftTimelinePage";
import { ShiftPatternsPage } from "./ShiftPatternsPage";
import { WeeklyTemplatesPage } from "./WeeklyTemplatesPage";
import type { ShiftTimelineResponse } from "../lib/types";

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
const monthlyMatrix = {
  plan: { id: "m1", location: "l1", location_name: "本館", year: 2028, month: 2, name: "2028年2月 本館シフト" },
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
    expect(screen.getByRole("link", { name: "自分の公開シフト" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "週間テンプレート" })).toBeInTheDocument();
  });

  it("shows my published shifts from snapshot API", async () => {
    mockAuthAndApi(["staff"], {
      "/api/v1/my-published-shifts/": {
        count: 1,
        next: null,
        previous: null,
        results: [
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
    expect(await screen.findByText("自分の公開シフト")).toBeInTheDocument();
    expect(await screen.findByText("2028-02-01")).toBeInTheDocument();
    expect(screen.getByText("本館")).toBeInTheDocument();
    expect(screen.getByText("08:30~17:00")).toBeInTheDocument();
    expect(screen.getByText("公開備考")).toBeInTheDocument();
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
    expect(addDaysToIsoDate.toString()).not.toContain("toISOString");
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
    expect(document.body.textContent).toContain("29");
    await userEvent.click(screen.getByText("早"));
    expect(await screen.findByText("2028-02-01")).toBeInTheDocument();
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
