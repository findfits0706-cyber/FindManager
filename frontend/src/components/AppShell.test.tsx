import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { AppShell } from "./AppShell";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function mockAuthUser(roles: string[]) {
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
    return { ok: true, json: async () => ({}) } as Response;
  });
}

function renderShell() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<AppShell />}>
            <Route index element={<div>home</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("shows read-only operation menus for shift managers and supervisors", async () => {
    mockAuthUser(["shift_manager"]);
    renderShell();
    expect(await screen.findByRole("link", { name: "スタッフ管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "拠点管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "業務エリア" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "業務カテゴリ" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "業務種別" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "業務種別適用" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "スタッフ所属" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "スタッフ対応可能業務" })).toBeInTheDocument();
  });

  it("shows the same navigation set for supervisors in read-only mode", async () => {
    mockAuthUser(["supervisor"]);
    renderShell();
    expect(await screen.findByRole("link", { name: "スタッフ管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "拠点管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "スタッフ所属" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "スタッフ対応可能業務" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "自分の所属" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "自分の対応可能業務" })).toBeInTheDocument();
  });

  it("shows self pages only for staff users", async () => {
    mockAuthUser(["staff"]);
    renderShell();
    expect(await screen.findByRole("link", { name: "自分の所属" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "自分の対応可能業務" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "スタッフ管理" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "拠点管理" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "スタッフ所属" })).not.toBeInTheDocument();
  });
});
