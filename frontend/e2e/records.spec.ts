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

  test("should display new record form", async ({ page }) => {
    await page.goto(`/members/${memberId}/records/new`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("#record_date")).toBeVisible();
    await expect(page.locator("#clinical_data")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create Record" })).toBeVisible();
  });

  test("should fill and submit record form", async ({ page }) => {
    await page.goto(`/members/${memberId}/records/new`);
    await page.waitForLoadState("networkidle");
    await page.locator("#record_date").fill("2026-04-01");
    await page.locator("#clinical_data").fill("Routine checkup");
    await page.locator("#diagnosis").fill("Healthy");
    await page.getByRole("button", { name: "Create Record" }).click();
    await expect(page).toHaveURL(/\/records/, { timeout: 10000 });
  });

  test("should show optional time field", async ({ page }) => {
    await page.goto(`/members/${memberId}/records/new`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("#record_time")).toBeVisible();
  });
});
