import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers/auth";

// The reminders list lives as a tab on the People page (/people?tab=reminders);
// there is no standalone /reminders route.
const REMINDERS_LIST = "/people?tab=reminders";

test.describe("Reminders", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, "e2e_reminders_user");
  });

  test.describe("Reminders list", () => {
    test("should navigate to reminders tab", async ({ page }) => {
      await page.goto(REMINDERS_LIST);
      await expect(page).toHaveURL(/\/people/);
      await expect(page).toHaveURL(/tab=reminders/);
    });

    test("should show New Reminder button", async ({ page }) => {
      await page.goto(REMINDERS_LIST);
      await expect(page.getByRole("link", { name: "New Reminder" })).toBeVisible({
        timeout: 10000,
      });
    });
  });

  test.describe("Create reminder", () => {
    test("should display new reminder form", async ({ page }) => {
      await page.goto("/reminders/new");
      await expect(page.locator("#title")).toBeVisible();
      await expect(page.locator("#description")).toBeVisible();
      await expect(page.locator("#start_datetime")).toBeVisible();
      await expect(page.getByRole("button", { name: "Create Reminder" })).toBeVisible();
    });

    test("should fill and submit reminder form", async ({ page }) => {
      test.setTimeout(60000);
      await page.goto("/reminders/new");
      await page.waitForLoadState("networkidle");

      await page.locator("#title").fill("Doctor Appointment");
      await page.locator("#description").fill("Annual checkup with Dr. Smith");
      await page.locator("#start_datetime").fill("2026-04-15T10:00");

      // reminder_type + schedule_type are Base UI Selects bound via RHF setValue.
      const triggers = page.locator('[data-slot="select-trigger"]');
      await triggers.filter({ hasText: "Select type" }).click();
      await page.getByRole("option").first().click();
      await triggers.filter({ hasText: "Select schedule" }).click();
      await page.getByRole("option").first().click();

      await page.getByRole("button", { name: "Create Reminder" }).click();
      // After the fix, creating a reminder returns to the People/reminders tab.
      await expect(page).toHaveURL(/tab=reminders/, { timeout: 15000 });
    });
  });
});
