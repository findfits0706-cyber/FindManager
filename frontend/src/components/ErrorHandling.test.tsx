import "@testing-library/jest-dom/vitest";
import { act, render, screen } from "@testing-library/react";
import { API_ERROR_EVENT, SESSION_EXPIRED_EVENT, type ApiErrorDetail } from "../api/client";
import { ErrorBoundary } from "./ErrorBoundary";
import { GlobalErrorNotice } from "./GlobalErrorNotice";

function ThrowingComponent(): never {
  throw new Error("render failure");
}

const detail: ApiErrorDetail = {
  status: 500,
  code: "server_error",
  message: "処理に失敗しました。",
  requestId: "request-visible",
  errors: {},
};

describe("global error handling", () => {
  it("shows a reload path when rendering fails", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("画面を表示できませんでした");
    expect(screen.getByRole("button", { name: "再読み込み" })).toBeEnabled();
    consoleError.mockRestore();
  });

  it("shows communication errors and request IDs", () => {
    render(<GlobalErrorNotice />);
    act(() => window.dispatchEvent(new CustomEvent(API_ERROR_EVENT, { detail })));
    expect(screen.getByRole("alert")).toHaveTextContent("処理に失敗しました。");
    expect(screen.getByText("Request ID: request-visible")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "再読み込み" })).toBeEnabled();
  });

  it("shows a dedicated session expiration message", () => {
    render(<GlobalErrorNotice />);
    act(() => window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT, { detail })));
    expect(screen.getByRole("alert")).toHaveTextContent("セッションの有効期限が切れました");
    expect(screen.getByText("再度ログインしてください。")).toBeInTheDocument();
  });
});
