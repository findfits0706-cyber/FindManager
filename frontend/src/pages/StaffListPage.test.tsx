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

const authUser = {
  id: "1",
  username: "system_admin",
  display_name: "Admin",
  employee_code: "EMP-1",
  email: "",
  employment_status: "active",
  must_change_password: false,
  roles: ["system_admin"],
  permissions: ["accounts.manage_staff_basic"],
};

const staffList = {
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
};

function jsonResponse(body: unknown, status = 200, requestId?: string): Response {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (requestId) headers.set("X-Request-ID", requestId);
  const text = JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    headers,
    json: async () => body,
    text: async () => text,
  } as Response;
}

function mockAuthAndStaff(staffResponse: () => Response | Promise<Response>) {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/v1/auth/me/")) return jsonResponse(authUser);
    return staffResponse();
  });
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
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
    confirmMock.mockReset();
  });

  it("renders staff list", async () => {
    mockAuthAndStaff(() => jsonResponse(staffList));

    renderPage();

    expect(await screen.findByRole("heading", { name: "Staff" })).toBeInTheDocument();
    expect(await screen.findByText("EMP-2")).toBeInTheDocument();
  });

  it("shows confirm dialog before deactivation", async () => {
    confirmMock.mockReturnValueOnce(true);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me/")) return jsonResponse(authUser);
      if (url.endsWith("/api/v1/auth/csrf/")) return jsonResponse({ csrfToken: "token" });
      if (url.endsWith("/deactivate/")) return jsonResponse({});
      return jsonResponse(staffList);
    });

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate" }));

    await waitFor(() => {
      expect(confirmMock).toHaveBeenCalled();
    });
  });

  it("shows a Japanese permission error and HTTP status for 403", async () => {
    mockAuthAndStaff(() =>
      jsonResponse(
        {
          detail: "このアクションを実行する権限がありません。",
          code: "permission_denied",
          message: "このアクションを実行する権限がありません。",
          errors: {},
        },
        403,
      ),
    );

    renderPage();

    expect(await screen.findByRole("heading", { name: "スタッフ一覧を取得できませんでした。" })).toBeVisible();
    expect(screen.getByText("このアクションを実行する権限がありません。")).toBeVisible();
    expect(screen.getByText("HTTPステータス: 403")).toBeVisible();
    expect(screen.queryByText("Failed to load staff.")).not.toBeInTheDocument();
  });

  it("shows the request ID for a 500 response", async () => {
    mockAuthAndStaff(() =>
      jsonResponse(
        {
          detail: "サーバーエラーが発生しました。",
          code: "server_error",
          message: "サーバーエラーが発生しました。",
          errors: {},
          request_id: "req-500",
        },
        500,
      ),
    );

    renderPage();

    expect(await screen.findByText("サーバーエラーが発生しました。")).toBeVisible();
    expect(screen.getByText("HTTPステータス: 500")).toBeVisible();
    expect(screen.getByText("リクエストID: req-500")).toBeVisible();
  });

  it("shows a Japanese message for a network error", async () => {
    mockAuthAndStaff(() => Promise.reject(new TypeError("Failed to fetch")));

    renderPage();

    expect(await screen.findByText("サーバーと通信できませんでした。接続を確認して再度お試しください。")).toBeVisible();
    expect(screen.queryByText(/HTTPステータス:/)).not.toBeInTheDocument();
  });

  it("refetches the staff list with the reload button", async () => {
    let staffRequests = 0;
    mockAuthAndStaff(() => {
      staffRequests += 1;
      if (staffRequests === 1) {
        return jsonResponse({ detail: "一時的なエラーです。" }, 500, "req-retry");
      }
      return jsonResponse(staffList);
    });

    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "再読込" }));

    expect(await screen.findByText("EMP-2")).toBeVisible();
    expect(staffRequests).toBe(2);
  });
});
