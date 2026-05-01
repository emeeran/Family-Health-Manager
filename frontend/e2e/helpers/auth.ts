import { expect, type Page } from "@playwright/test";

const API_BASE = "http://localhost:3000/api/v1";
export const TEST_PASSWORD = "TestPass1!";

export async function registerAndLogin(page: Page, username: string): Promise<void> {
  // Register (ignore if user already exists)
  const regRes = await page.request.post(`${API_BASE}/auth/register`, {
    data: { username, password: TEST_PASSWORD },
    failOnStatusCode: false,
  });

  // Login via API with retry on rate limit
  let token: string | undefined;
  for (let attempt = 0; attempt < 6; attempt++) {
    const res = await page.request.post(`${API_BASE}/auth/login`, {
      data: { username, password: TEST_PASSWORD },
      failOnStatusCode: false,
    });

    if (res.ok()) {
      const body = await res.json();
      token = body.access_token;
      break;
    }

    if (res.status() === 429) {
      const delay = 500 * Math.pow(2, attempt);
      await new Promise((r) => setTimeout(r, delay));
      continue;
    }

    throw new Error(
      `Login failed for ${username}: ${res.status()} (register was ${regRes.status()})`
    );
  }

  if (!token) {
    throw new Error(`No token for ${username} after retries (register was ${regRes.status()})`);
  }

  await page.context().addCookies([
    {
      name: "session_token",
      value: token,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      secure: false,
      sameSite: "Lax" as const,
    },
  ]);

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 10000 });
}

/** Create a family member via the API (for test setup) */
export async function createMemberViaApi(
  page: Page,
  member: { first_name: string; last_name: string; date_of_birth: string }
): Promise<string> {
  const token = await getToken(page);
  for (let attempt = 0; attempt < 8; attempt++) {
    const res = await page.request.post(`http://127.0.0.1:8000/api/v1/members?token=${token}`, {
      data: {
        ...member,
        gender: "prefer_not_to_say",
        relationship: "self",
      },
      failOnStatusCode: false,
    });
    if (res.ok()) {
      const body = await res.json();
      return body.id;
    }
    if (res.status() === 429) {
      const delay = 1000 * (attempt + 1);
      await new Promise((r) => setTimeout(r, delay));
      continue;
    }
    const body = await res.text();
    throw new Error(`Failed to create member: ${res.status()} ${body}`);
  }
  throw new Error("Failed to create member after retries (rate limited)");
}

/** Fill required member form fields and set gender/relationship */
export async function fillMemberForm(
  page: Page,
  data: { first_name: string; last_name: string; date_of_birth: string }
): Promise<void> {
  await page.locator("#first_name").fill(data.first_name);
  await page.locator("#last_name").fill(data.last_name);
  await page.locator("#date_of_birth").fill(data.date_of_birth);

  // Set hidden inputs directly (Base UI Select is hard to automate)
  await page.evaluate(() => {
    const gender = document.querySelector<HTMLInputElement>('input[name="gender"]');
    const relationship = document.querySelector<HTMLInputElement>('input[name="relationship"]');
    if (gender) gender.value = "prefer_not_to_say";
    if (relationship) relationship.value = "self";
  });
}

/** Get the auth token from the current page's cookies */
export async function getToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "session_token");
  if (!session) throw new Error("No session_token cookie found");
  return session.value;
}
