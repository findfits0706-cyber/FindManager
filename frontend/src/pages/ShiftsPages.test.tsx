import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { AppShell } from "../components/AppShell";
import { AuthProvider } from "../features/auth/AuthContext";
import { labelToOffset, offsetToLabel } from "../lib/timeOffsets";
import { ShiftPatternsPage } from "./ShiftPatternsPage";
import { WeeklyTemplatesPage } from "./WeeklyTemplatesPage";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const confirmMock = vi.spyOn(window, "confirm");

function renderWithAuth(element: ReactNode) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
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
        return { ok: true, json: async () => (typeof payload === "function" ? payload(input, init) : payload) } as Response;
      }
    }
    return { ok: true, json: async () => ({ count: 0, next: null, previous: null, results: [] }) } as Response;
  });
}

const locations = { count: 1, next: null, previous: null, results: [{ id: "l1", name: "本館", is_active: true }] };
const workTypes = {
  count: 1,
  next: null,
  previous: null,
  results: [{ id: "w1", name: "ジム業務", short_name: "ジム", color_key: "blue", is_active: true }],
};
const workAreas = { count: 1, next: null, previous: null, results: [{ id: "a1", location: "l1", name: "ジム", is_active: true }] };
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
    fetchMock.mockReset();
    confirmMock.mockReset();
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
    expect(screen.getByRole("link", { name: "週間テンプレート" })).toBeInTheDocument();
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
    expect(screen.getAllByRole("option", { name: "早" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("option", { name: "他" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "スタッフA" })).not.toBeInTheDocument();
  });
});
