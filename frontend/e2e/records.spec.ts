import { test, expect } from "@playwright/test";
import { registerAndLogin, createMemberViaApi } from "./helpers/auth";

test.describe("Health Records", () => {
  let memberId: string;

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, "e2e_records_user");
    await page.waitForTimeout(1000); // Wait for rate limiter to reset
    memberId = await createMemberViaApi(page, {
      first_name: "Record",
      last_name: "Patient",
      date_of_birth: "1990-01-01",
    });
  });

  test("should load the new-record page in wizard mode", async ({ page }) => {
    await page.goto(`/people/${memberId}/records/new`);
    // The page defaults to the wizard; the toggle offers a switch to classic form.
    await expect(page.getByRole("button", { name: /switch to classic form/i })).toBeVisible({
      timeout: 10000,
    });
  });

  test("should switch to classic form and show core fields", async ({ page }) => {
    await page.goto(`/people/${memberId}/records/new`);
    await page.getByRole("button", { name: /switch to classic form/i }).click();
    await expect(page.locator("#record_date")).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole("button", { name: /create record/i })).toBeVisible();
  });

  // NOTE: deeper classic-form submit coverage is limited because most fields
  // (clinical_data, diagnosis, record_time) are rendered conditionally based on
  // the selected record_type's schema, and record_type uses a Base UI Select
  // that doesn't drive reliably under Playwright (see the member-form skip).
});
