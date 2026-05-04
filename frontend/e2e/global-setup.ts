import { request } from "@playwright/test";

const API_BASE = "http://localhost:3000/api/v1";
export const TEST_PASSWORD = "TestPass1!";

const TEST_USERS = [
  "e2e_auth_user",
  "e2e_nav_user",
  "e2e_members_user",
  "e2e_records_user",
  "e2e_reminders_user",
];

async function globalSetup() {
  const apiRequest = await request.newContext();
  for (const username of TEST_USERS) {
    // Register — ignore if already exists
    await apiRequest.post(`${API_BASE}/auth/register`, {
      data: { username, password: TEST_PASSWORD },
      failOnStatusCode: false,
    });
    console.error(`Pre-registered ${username}`);
  }
  await apiRequest.dispose();
}

export default globalSetup;
