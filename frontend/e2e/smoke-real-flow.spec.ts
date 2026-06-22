import { test, expect, type Page } from "@playwright/test";

const API_BASE = "http://localhost:3000/api/v1";
const PASSWORD = "TestPass1!";

// Unique per-run so collisions with prior runs can't cause false failures.
const SUFFIX = Math.random().toString(36).slice(2, 8);
const USERNAME = `smoke_${SUFFIX}`;
const MEMBER = {
  first_name: `Smoke${SUFFIX}`,
  last_name: "User",
  date_of_birth: "1990-04-20",
  gender: "prefer_not_to_say",
  relationship: "self",
};

async function registerLoginAndGetToken(page: Page): Promise<string> {
  await page.request.post(`${API_BASE}/auth/register`, {
    data: { username: USERNAME, password: PASSWORD },
    failOnStatusCode: false,
  });
  const res = await page.request.post(`${API_BASE}/auth/login`, {
    data: { username: USERNAME, password: PASSWORD },
  });
  expect(res.ok(), `login failed: ${res.status()}`).toBeTruthy();
  const { access_token } = await res.json();

  await page.context().addCookies([
    {
      name: "session_token",
      value: access_token,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      secure: false,
      sameSite: "Lax" as const,
    },
  ]);
  return access_token;
}

// Real end-to-end smoke test of the primary user journey. Proves the running
// app (frontend + backend) actually works after the debloat, independent of the
// rotted legacy specs that reference pre-refactor routes/labels.
test.describe("Real-flow smoke (post-refactor app)", () => {
  test("register → create member → see them across Home, People, and detail", async ({ page }) => {
    test.setTimeout(60_000);
    const token = await registerLoginAndGetToken(page);

    // Create a member through the public API (the same call the UI makes).
    const createRes = await page.request.post(`${API_BASE}/members?token=${token}`, {
      data: MEMBER,
    });
    expect(createRes.ok(), `member create failed: ${createRes.status()}`).toBeTruthy();
    const member = await createRes.json();

    // 1. Home (/) — with a member present, the onboarding redirect must NOT
    //    fire; the dashboard/home content should render and show the member.
    await page.goto("/");
    await expect(page).toHaveURL(/\/$/, { timeout: 10_000 });
    await expect(page.getByText(MEMBER.first_name).first()).toBeVisible({ timeout: 15_000 });

    // 2. People list (/people) — member card should be visible.
    await page.goto("/people");
    await expect(page).toHaveURL(/\/people/);
    await expect(page.getByText(MEMBER.first_name).first()).toBeVisible({ timeout: 15_000 });

    // 3. Member detail (/people/:id) — the member's page renders.
    await page.goto(`/people/${member.id}`);
    await expect(page).toHaveURL(new RegExp(`/people/${member.id}`));
    await expect(page.getByText(MEMBER.first_name).first()).toBeVisible({ timeout: 15_000 });
  });
});
