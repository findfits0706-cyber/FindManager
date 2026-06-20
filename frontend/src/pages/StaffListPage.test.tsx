import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { StaffListPage } from "./StaffListPage";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
const confirmMock = vi.spyOn(window, "confirm");

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BrowserRouter>
        <AuthProvider>
          <StaffListPage />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

describe("StaffListPage", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("renders staff list", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me/")) {
        return {
          ok: true,
          json: async () => ({
            id: "1",
            username: "system_admin",
            display_name: "Admin",
            employee_code: "EMP-1",
            email: "",
            employment_status: "active",
            must_change_password: false,
            roles: ["system_admin"],
            permissions: ["accounts.manage_staff_basic"],
          }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "2",
              username: "staff",
              display_name: "Staff",
              employee_code: "EMP-2",
              email: "",
              employment_status: "active",
              hire_date: null,
              termination_date: null,
              must_change_password: false,
              is_active: true,
              roles: ["staff"],
            },
          ],
        }),
      } as Response;
    });

    renderPage();
    expect(await screen.findByText("Staff")).toBeInTheDocument();
  });

  it("shows confirm dialog before deactivation", async () => {
    confirmMock.mockReturnValueOnce(true);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me/")) {
        return {
          ok: true,
          json: async () => ({
            id: "1",
            username: "system_admin",
            display_name: "Admin",
            employee_code: "EMP-1",
            email: "",
            employment_status: "active",
            must_change_password: false,
            roles: ["system_admin"],
            permissions: ["accounts.manage_staff_basic"],
          }),
        } as Response;
      }
      if (url.endsWith("/api/v1/auth/csrf/")) {
        return { ok: true, json: async () => ({ csrfToken: "token" }) } as Response;
      }
      if (url.endsWith("/deactivate/")) {
        return { ok: true, json: async () => ({}) } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "2",
              username: "staff",
              display_name: "Staff",
              employee_code: "EMP-2",
              email: "",
              employment_status: "active",
              hire_date: null,
              termination_date: null,
              must_change_password: false,
              is_active: true,
              roles: ["staff"],
            },
          ],
        }),
      } as Response;
    });

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "利用停止" }));
    await waitFor(() => {
      expect(confirmMock).toHaveBeenCalled();
    });
  });
});
