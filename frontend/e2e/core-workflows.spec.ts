import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD ?? "DevPassword123!";

function dateInTokyo() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

const WORK_DATE = dateInTokyo();
const YEAR = Number(WORK_DATE.slice(0, 4));
const MONTH = Number(WORK_DATE.slice(5, 7));
const MONTH_PREFIX = WORK_DATE.slice(0, 7);
const MONTH_START = `${MONTH_PREFIX}-01`;
const MONTH_END = `${MONTH_PREFIX}-${String(new Date(Date.UTC(YEAR, MONTH, 0)).getUTCDate()).padStart(2, "0")}`;
const OTHER_WORK_DATE = WORK_DATE === MONTH_START ? `${MONTH_PREFIX}-02` : MONTH_START;

const state: Record<string, string> = {};

// Live API workflow responses intentionally span multiple domain-specific shapes.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type JsonObject = Record<string, any>;

async function csrf(page: Page) {
  const response = await page.request.get("/api/v1/auth/csrf/");
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { csrfToken: string }).csrfToken;
}

async function requestJson(
  page: Page,
  method: "POST" | "PUT" | "PATCH",
  path: string,
  data: JsonObject,
  expectedStatus: number | number[] = [200, 201],
) {
  const response = await page.request.fetch(path, {
    method,
    data,
    headers: { "X-CSRFToken": await csrf(page) },
  });
  const text = await response.text();
  const expected = Array.isArray(expectedStatus) ? expectedStatus : [expectedStatus];
  expect(expected, `${method} ${path}: ${text}`).toContain(response.status());
  return text ? (JSON.parse(text) as JsonObject) : {};
}

async function getJson(page: Page, path: string) {
  const response = await page.request.get(path);
  const text = await response.text();
  expect(response.ok(), `GET ${path}: ${text}`).toBe(true);
  return text ? (JSON.parse(text) as JsonObject) : {};
}

async function loginApi(page: Page, username: string) {
  return requestJson(page, "POST", "/api/v1/auth/login/", { username, password: PASSWORD }, 200);
}

function results(payload: JsonObject): JsonObject[] {
  return Array.isArray(payload) ? payload : payload.results;
}

test.describe.serial("FindManager release candidate workflows", () => {
  test("authentication: login, logout, and unauthorized financial route", async ({ page }) => {
    await page.goto("/finance/performance");
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel("Username").fill("staff");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign In" }).click();
    await expect(page).toHaveURL(/\/staff$/);
    await page.goto("/finance/performance");
    await expect(page.getByRole("heading", { name: "このページを表示する権限がありません" })).toBeVisible();

    await loginApi(page, "system_admin");
    await page.goto("/system/status");
    await expect(page.getByRole("heading", { name: "システム状態" })).toBeVisible();
    await page.getByRole("button", { name: "ログアウト" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("shift: create assignment, confirm, publish, and staff view", async ({ page }) => {
    await loginApi(page, "system_admin");
    const locationList = await getJson(page, "/api/v1/locations/?page_size=100");
    state.location = results(locationList).find((item) => item.code === "main")!.id;
    state.outsideLocation = results(locationList).find((item) => item.code === "findfits")!.id;
    const staffList = await getJson(page, "/api/v1/staff/?page_size=100");
    state.staff = results(staffList).find((item) => item.username === "staff")!.id;
    state.shiftManager = results(staffList).find((item) => item.username === "shift_manager")!.id;
    const patterns = await getJson(page, `/api/v1/shift-patterns/?location=${state.location}&page_size=100`);
    state.pattern = results(patterns).find((item) => item.code === "gym_early")!.id;

    const plan = await requestJson(page, "POST", "/api/v1/monthly-shift-plans/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      name: "E2E 月間シフト",
      notes: "",
    });
    state.plan = plan.id;
    const assignment = await requestJson(page, "POST", "/api/v1/monthly-shift-assignments/", {
      monthly_shift_plan: state.plan,
      work_date: WORK_DATE,
      staff: state.staff,
      shift_pattern: state.pattern,
      notes: "",
    });
    state.assignment = assignment.id;
    const preview = await requestJson(
      page,
      "POST",
      `/api/v1/monthly-shift-plans/${state.plan}/publication-preview/`,
      {},
      200,
    );
    expect(preview.can_confirm).toBe(true);
    await requestJson(
      page,
      "POST",
      `/api/v1/monthly-shift-plans/${state.plan}/confirm/`,
      { acknowledge_warnings: true },
      200,
    );
    const published = await requestJson(
      page,
      "POST",
      `/api/v1/monthly-shift-plans/${state.plan}/publish/`,
      { acknowledge_warnings: true },
      201,
    );
    state.publication = published.publication.id;
    const publication = await getJson(page, `/api/v1/monthly-shift-publications/${state.publication}/`);
    state.publicationAssignment = publication.assignments[0].id;

    await loginApi(page, "staff");
    const mine = await getJson(page, `/api/v1/my-published-shifts/?date_from=${WORK_DATE}&date_to=${WORK_DATE}`);
    expect(mine.shifts).toHaveLength(1);
    expect(mine.shifts[0].staff).toBe(state.staff);
  });

  test("shift requests: staff submits and manager reviews", async ({ page }) => {
    await loginApi(page, "system_admin");
    const now = Date.now();
    const period = await requestJson(page, "POST", "/api/v1/shift-request-periods/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      name: "E2E 希望提出",
      description: "",
      opens_at: new Date(now - 86_400_000).toISOString(),
      closes_at: new Date(now + 7 * 86_400_000).toISOString(),
    });
    state.requestPeriod = period.id;
    await requestJson(page, "POST", `/api/v1/shift-request-periods/${period.id}/open/`, {}, 200);

    await loginApi(page, "staff");
    await requestJson(page, "PUT", `/api/v1/my-shift-request-periods/${period.id}/submission/`, {
      notes: "E2E希望",
      items: [
        {
          request_type: "unavailable",
          work_date: OTHER_WORK_DATE,
          start_offset_minutes: 1080,
          end_offset_minutes: 1320,
          priority: "normal",
          reason: "E2E",
          notes: "",
        },
      ],
    });
    const submitted = await requestJson(
      page,
      "POST",
      `/api/v1/my-shift-request-periods/${period.id}/submit/`,
      {},
      200,
    );
    expect(submitted.status).toBe("submitted");

    await loginApi(page, "system_admin");
    const submissions = await getJson(page, `/api/v1/shift-request-submissions/?request_period=${period.id}`);
    expect(results(submissions).some((item) => item.staff === state.staff && item.status === "submitted")).toBe(true);
  });

  test("attendance: clock, correction approval/apply, and confirm", async ({ page }) => {
    await loginApi(page, "staff");
    const outsideLocation = await requestJson(page, "POST", "/api/v1/my-attendance/clock-in/", {
      location: state.outsideLocation,
      work_date: WORK_DATE,
    }, 400);
    expect(outsideLocation.code).toBe("validation_error");
    expect(outsideLocation.errors.location).toBeTruthy();

    await page.goto("/shifts/my-published");
    await expect(page.getByRole("heading", { name: "自分のシフト" })).toBeVisible();
    await page.getByLabel("年").fill(String(YEAR));
    await page.getByLabel("月").fill(String(MONTH));
    await expect(page.getByRole("button", { name: WORK_DATE })).toBeVisible();
    const clockInRequestPromise = page.waitForRequest(
      (request) => request.method() === "POST" && request.url().endsWith("/api/v1/my-attendance/clock-in/"),
    );
    const clockInResponsePromise = page.waitForResponse(
      (response) => response.request().method() === "POST" && response.url().endsWith("/api/v1/my-attendance/clock-in/"),
    );
    await page.getByRole("button", { name: "出勤", exact: true }).click();
    const clockInRequest = await clockInRequestPromise;
    expect(clockInRequest.postDataJSON()).toEqual({
      location: state.location,
      work_date: WORK_DATE,
    });
    expect(clockInRequest.postDataJSON()).not.toHaveProperty("occurred_at");
    const clockInResponse = await clockInResponsePromise;
    expect(clockInResponse.status()).toBe(201);
    const clockedIn = (await clockInResponse.json()) as JsonObject;
    expect(clockedIn.actual_clock_in_at).toBeTruthy();
    state.attendance = clockedIn.id;
    await expect(page.getByText(/出勤済み/)).toBeVisible();
    await requestJson(page, "POST", `/api/v1/my-attendance/${state.attendance}/break-start/`, {}, 200);
    await requestJson(page, "POST", `/api/v1/my-attendance/${state.attendance}/break-end/`, {}, 200);
    const clockedOut = await requestJson(
      page,
      "POST",
      `/api/v1/my-attendance/${state.attendance}/clock-out/`,
      {},
      200,
    );
    const clockInEvent = clockedOut.events.find((event: JsonObject) => event.event_type === "clock_in");
    expect(clockInEvent.occurred_at).toBe(clockedIn.actual_clock_in_at);

    await page.goto("/my/attendance");
    await page.getByLabel("年").fill(String(YEAR));
    await page.getByLabel("月").fill(String(MONTH));
    await page.getByRole("button", { name: WORK_DATE }).click();
    await expect(page.getByText(clockInEvent.occurred_at, { exact: true })).toBeVisible();

    const correction = await requestJson(page, "POST", "/api/v1/my-attendance-corrections/", {
      attendance_record: state.attendance,
      requested_clock_in_at: `${WORK_DATE}T09:15:00+09:00`,
      requested_clock_out_at: `${WORK_DATE}T17:15:00+09:00`,
      requested_break_minutes: 60,
      reason: "E2E修正",
    }, 201);
    state.correction = correction.id;
    await requestJson(page, "POST", `/api/v1/my-attendance-corrections/${correction.id}/submit/`, {}, 200);

    await loginApi(page, "system_admin");
    await requestJson(page, "POST", `/api/v1/attendance-correction-requests/${correction.id}/approve/`, {
      manager_note: "E2E承認",
    }, 200);
    const applied = await requestJson(page, "POST", `/api/v1/attendance-correction-requests/${correction.id}/apply/`, {
      manager_note: "E2E反映",
    }, 200);
    expect(applied.status).toBe("applied");
    const confirmed = await requestJson(page, "POST", `/api/v1/attendance-records/${state.attendance}/confirm/`, {
      manager_note: "E2E確認",
    }, 200);
    expect(confirmed.status).toBe("confirmed");
  });

  test("monthly close: preview, acknowledge warnings, close, and reject mutation", async ({ page }) => {
    await loginApi(page, "system_admin");
    const period = await requestJson(page, "POST", "/api/v1/attendance-closing-periods/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      name: "E2E 月次勤怠締め",
    });
    state.closing = period.id;
    const preview = await requestJson(page, "POST", `/api/v1/attendance-closing-periods/${period.id}/preview/`, {}, 200);
    const closed = await requestJson(page, "POST", `/api/v1/attendance-closing-periods/${period.id}/close/`, {
      acknowledge_warnings: true,
      validation_fingerprint: preview.validation_fingerprint,
      manager_note: "E2E締め",
    }, 200);
    expect(closed.status).toBe("closed");

    await loginApi(page, "staff");
    const rejected = await requestJson(page, "POST", "/api/v1/my-attendance/clock-in/", {
      location: state.location,
      work_date: OTHER_WORK_DATE,
    }, 400);
    expect(rejected.code).toBe("validation_error");
  });

  test("labor estimate: rate, allowance, preview, and finalize", async ({ page }) => {
    await loginApi(page, "system_admin");
    await requestJson(page, "POST", "/api/v1/staff-compensation-profiles/", {
      location: state.location,
      staff: state.staff,
      employment_type: "hourly",
      base_hourly_rate: "1200.00",
      valid_from: MONTH_START,
      valid_to: MONTH_END,
      notes: "E2E",
    });
    await requestJson(page, "POST", "/api/v1/staff-allowance-assignments/", {
      location: state.location,
      staff: state.staff,
      code: "e2e-day",
      name: "E2E日額手当",
      allowance_type: "per_worked_day",
      amount: "500.00",
      valid_from: MONTH_START,
      valid_to: MONTH_END,
    });
    const period = await requestJson(page, "POST", "/api/v1/labor-cost-estimate-periods/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      attendance_closing_period: state.closing,
      name: "E2E 概算人件費",
    });
    state.laborEstimate = period.id;
    const preview = await requestJson(page, "POST", `/api/v1/labor-cost-estimate-periods/${period.id}/preview/`, {}, 200);
    expect(preview.source_status).toBe("closed");
    expect(preview.summary.error_count).toBe(0);
    const finalized = await requestJson(page, "POST", `/api/v1/labor-cost-estimate-periods/${period.id}/finalize/`, {
      acknowledge_warnings: true,
      validation_fingerprint: preview.validation_fingerprint,
      manager_note: "E2E確定",
    }, 200);
    expect(finalized.status).toBe("finalized");
  });

  test("labor budget: create, preview, approve, and show variance", async ({ page }) => {
    await loginApi(page, "system_admin");
    const period = await requestJson(page, "POST", "/api/v1/labor-cost-budget-periods/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      budget_amount: "500000.00",
      warning_threshold_percent: "90.00",
      critical_threshold_percent: "100.00",
      name: "E2E 人件費予算",
    });
    state.laborBudget = period.id;
    const preview = await requestJson(page, "POST", `/api/v1/labor-cost-budget-periods/${period.id}/preview/`, {}, 200);
    expect(preview.can_approve).toBe(true);
    const approved = await requestJson(page, "POST", `/api/v1/labor-cost-budget-periods/${period.id}/approve/`, {
      acknowledge_warnings: true,
      validation_fingerprint: preview.validation_fingerprint,
      manager_note: "E2E承認",
    }, 200);
    expect(approved.status).toBe("approved");
    const variance = await getJson(page, `/api/v1/labor-cost-budget-periods/${period.id}/variance/`);
    expect(variance.summary.planned_total).toBeDefined();
  });

  test("revenue performance: category, budget approval, actual finalize, and summary", async ({ page }) => {
    await loginApi(page, "system_admin");
    const category = await requestJson(page, "POST", "/api/v1/revenue-categories/", {
      location: state.location,
      code: "e2e-membership",
      name: "E2E会費",
      short_name: "E2E会費",
      display_order: 10,
    });
    state.revenueCategory = category.id;
    const budget = await requestJson(page, "POST", "/api/v1/revenue-budget-periods/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      name: "E2E 売上予算",
    });
    state.revenueBudget = budget.id;
    await requestJson(page, "POST", "/api/v1/revenue-budget-lines/", {
      budget_period: budget.id,
      category: category.id,
      budget_amount: "1000000.00",
    });
    const budgetPreview = await requestJson(page, "POST", `/api/v1/revenue-budget-periods/${budget.id}/preview/`, {}, 200);
    await requestJson(page, "POST", `/api/v1/revenue-budget-periods/${budget.id}/approve/`, {
      acknowledge_warnings: true,
      validation_fingerprint: budgetPreview.validation_fingerprint,
    }, 200);

    const actual = await requestJson(page, "POST", "/api/v1/revenue-actual-periods/", {
      location: state.location,
      year: YEAR,
      month: MONTH,
      revenue_budget_period: budget.id,
      labor_cost_budget_period: state.laborBudget,
      labor_cost_estimate_period: state.laborEstimate,
      name: "E2E 売上実績",
    });
    state.revenueActual = actual.id;
    await requestJson(page, "POST", "/api/v1/revenue-actual-lines/", {
      actual_period: actual.id,
      category: category.id,
      actual_amount: "1100000.00",
      source: "manual",
    });
    const actualPreview = await requestJson(page, "POST", `/api/v1/revenue-actual-periods/${actual.id}/preview/`, {}, 200);
    const finalized = await requestJson(page, "POST", `/api/v1/revenue-actual-periods/${actual.id}/finalize/`, {
      acknowledge_warnings: true,
      validation_fingerprint: actualPreview.validation_fingerprint,
    }, 200);
    expect(finalized.status).toBe("finalized");
    const summary = await getJson(
      page,
      `/api/v1/financial-performance/?location=${state.location}&year=${YEAR}&month=${MONTH}`,
    );
    expect(summary.is_snapshot).toBe(true);
    expect(summary.summary.actual_labor_cost_ratio).not.toBeNull();
  });

  test("published shift change: staff requests and manager approves/applies", async ({ page }) => {
    await loginApi(page, "staff");
    const change = await requestJson(page, "POST", "/api/v1/my-shift-change-requests/", {
      publication_assignment: state.publicationAssignment,
      request_type: "drop_shift",
      priority: "high",
      requested_staff: state.shiftManager,
      reason: "E2E代行依頼",
      submit: true,
    }, 201);
    state.changeRequest = change.id;
    expect(change.status).toBe("submitted");

    await loginApi(page, "system_admin");
    await requestJson(page, "POST", `/api/v1/shift-change-requests/${change.id}/approve/`, {
      manager_note: "E2E承認",
    }, 200);
    const applied = await requestJson(page, "POST", `/api/v1/shift-change-requests/${change.id}/apply/`, {
      manager_note: "E2E反映",
    }, 200);
    expect(applied.status).toBe("applied");
  });
});
