import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { OperationsMasterPage } from "./OperationsMasterPage";
import { StaffAssignmentsPage } from "./StaffAssignmentsPage";
import { MyCapabilitiesPage } from "./MyCapabilitiesPage";

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
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/v1/auth/me/")) {
      return {
        ok: true,
        json: async () => ({
          id: "1",
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
    for (const [suffix, payload] of Object.entries(handlers)) {
      if (url.includes(suffix)) {
        return {
          ok: true,
          json: async () => payload,
        } as Response;
      }
    }
    return { ok: true, json: async () => ({}) } as Response;
  });
}

describe("Operations pages", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    confirmMock.mockReset();
  });

  it("shows Japanese capability level labels in staff assignments", async () => {
    mockAuthAndApi(
      ["shift_manager"],
      {
        "/api/v1/staff/?page_size=100": { count: 1, next: null, previous: null, results: [{ id: "s1", display_name: "スタッフA" }] },
        "/api/v1/locations/?page_size=100": { count: 1, next: null, previous: null, results: [{ id: "l1", name: "本館" }] },
        "/api/v1/work-types/?page_size=100": { count: 1, next: null, previous: null, results: [{ id: "w1", name: "受付対応" }] },
        "/api/v1/staff-capabilities/?page_size=100": {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "c1",
              staff: "s1",
              staff_display_name: "スタッフA",
              work_type: "w1",
              work_type_name: "受付対応",
              location: "l1",
              location_name: "本館",
              level: "trainer",
              valid_from: "2026-06-21",
              valid_until: null,
              is_active: true,
            },
          ],
        },
      },
    );

    renderWithAuth(<StaffAssignmentsPage resource="staff-capabilities" />);

    expect(await screen.findByRole("heading", { name: "スタッフ対応可能業務" })).toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: "研修中" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "補助付きで対応可能" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "単独対応可能" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("option", { name: "指導者" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("指導者").length).toBeGreaterThan(0);
  });

  it("shows Japanese capability level labels on my capabilities page", async () => {
    mockAuthAndApi(
      ["staff"],
      {
        "/api/v1/my-staff-locations/?page_size=100": { count: 0, next: null, previous: null, results: [] },
        "/api/v1/my-capabilities/?page_size=100": {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "c1",
              work_type_name: "ジムメニュー",
              location_name: "本館",
              level: "independent",
              valid_from: "2026-06-21",
              valid_until: null,
              approved_by_display_name: "管理者",
              approved_at: "2026-06-21T10:00:00+09:00",
              notes: "",
              is_active: true,
            },
          ],
        },
      },
    );

    renderWithAuth(<MyCapabilitiesPage />);
    expect(await screen.findByText("単独対応可能")).toBeInTheDocument();
  });

  it("asks for confirmation before changing master active state", async () => {
    confirmMock.mockReturnValueOnce(false);
    mockAuthAndApi(
      ["system_admin"],
      {
        "/api/v1/locations/?page_size=100": {
          count: 1,
          next: null,
          previous: null,
          results: [{ id: "l1", code: "main", name: "本館", short_name: "本館", timezone: "Asia/Tokyo", is_active: true }],
        },
        "/api/v1/work-categories/?page_size=100": { count: 0, next: null, previous: null, results: [] },
        "/api/v1/work-areas/?page_size=100": { count: 0, next: null, previous: null, results: [] },
        "/api/v1/work-types/?page_size=100": { count: 0, next: null, previous: null, results: [] },
      },
    );

    renderWithAuth(<OperationsMasterPage resource="locations" />);
    await userEvent.click(await screen.findByRole("button", { name: "無効化" }));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/deactivate/"))).toBe(false);
  });

  it("asks for confirmation before changing staff assignment active state", async () => {
    confirmMock.mockReturnValueOnce(false);
    mockAuthAndApi(
      ["shift_manager"],
      {
        "/api/v1/staff/?page_size=100": { count: 1, next: null, previous: null, results: [{ id: "s1", display_name: "スタッフA" }] },
        "/api/v1/locations/?page_size=100": { count: 1, next: null, previous: null, results: [{ id: "l1", name: "本館" }] },
        "/api/v1/staff-locations/?page_size=100": {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "sl1",
              staff: "s1",
              staff_display_name: "スタッフA",
              location: "l1",
              location_name: "本館",
              is_primary: true,
              valid_from: "2026-06-21",
              valid_until: null,
              is_active: true,
            },
          ],
        },
      },
    );

    renderWithAuth(<StaffAssignmentsPage resource="staff-locations" />);
    await userEvent.click(await screen.findByRole("button", { name: "無効化" }));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/deactivate/"))).toBe(false);
  });

  it("prevents duplicate master submissions while saving", async () => {
    let postCount = 0;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me/")) {
        return {
          ok: true,
          json: async () => ({
            id: "1",
            username: "admin",
            display_name: "管理者",
            employee_code: "EMP-1",
            email: "",
            employment_status: "active",
            must_change_password: false,
            roles: ["system_admin"],
            permissions: [],
          }),
        } as Response;
      }
      if (url.endsWith("/api/v1/auth/csrf/")) {
        return { ok: true, json: async () => ({ csrfToken: "token" }) } as Response;
      }
      if (url.endsWith("/api/v1/locations/") && init?.method === "POST") {
        postCount += 1;
        return new Promise<Response>(() => undefined);
      }
      if (url.includes("/api/v1/locations/?page_size=100")) {
        return { ok: true, json: async () => ({ count: 0, next: null, previous: null, results: [] }) } as Response;
      }
      return { ok: true, json: async () => ({ count: 0, next: null, previous: null, results: [] }) } as Response;
    });

    renderWithAuth(<OperationsMasterPage resource="locations" />);
    await userEvent.click(await screen.findByRole("button", { name: "新規作成" }));
    expect(await screen.findByRole("button", { name: "保存中..." })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "保存中..." }));
    expect(postCount).toBe(1);
  });

  it("prevents duplicate staff assignment submissions while saving", async () => {
    let postCount = 0;
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me/")) {
        return {
          ok: true,
          json: async () => ({
            id: "1",
            username: "manager",
            display_name: "管理者",
            employee_code: "EMP-1",
            email: "",
            employment_status: "active",
            must_change_password: false,
            roles: ["shift_manager"],
            permissions: [],
          }),
        } as Response;
      }
      if (url.endsWith("/api/v1/auth/csrf/")) {
        return { ok: true, json: async () => ({ csrfToken: "token" }) } as Response;
      }
      if (url.endsWith("/api/v1/staff-locations/") && init?.method === "POST") {
        postCount += 1;
        return new Promise<Response>(() => undefined);
      }
      return { ok: true, json: async () => ({ count: 0, next: null, previous: null, results: [] }) } as Response;
    });

    renderWithAuth(<StaffAssignmentsPage resource="staff-locations" />);
    await userEvent.click(await screen.findByRole("button", { name: "新規作成" }));
    expect(await screen.findByRole("button", { name: "保存中..." })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "保存中..." }));
    expect(postCount).toBe(1);
  });
});
