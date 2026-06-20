import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";
import { AuthProvider } from "../features/auth/AuthContext";
import { LoginPage } from "./LoginPage";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  it("renders form and submits", async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => ({ csrfToken: "token" }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: {
            id: "1",
            username: "staff",
            display_name: "Staff",
            employee_code: "EMP-1",
            email: "",
            employment_status: "active",
            must_change_password: false,
            roles: ["staff"],
            permissions: [],
          },
        }),
      });

    renderPage();
    await userEvent.type(screen.getByLabelText("ユーザー名"), "staff");
    await userEvent.type(screen.getByLabelText("パスワード"), "password");
    await userEvent.click(screen.getByRole("button", { name: "ログイン" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(3);
    });
  });

  it("shows login error", async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: "unauthorized" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ csrfToken: "token" }) })
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: "ログイン失敗" }) });

    renderPage();
    await userEvent.type(screen.getByLabelText("ユーザー名"), "staff");
    await userEvent.type(screen.getByLabelText("パスワード"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "ログイン" }));
    expect(await screen.findByText("ログイン失敗")).toBeInTheDocument();
  });
});
