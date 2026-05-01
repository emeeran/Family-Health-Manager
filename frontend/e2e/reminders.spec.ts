import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers/auth";

test.describe("Reminders", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, "e2e_reminders_user");
  });

  test.describe("Reminders list", () => {
    test("should navigate to reminders page", async ({ page }) => {
      await page.getByRole("link", { name: "Reminders" }).click();
      await expect(page).toHaveURL(/\/reminders/);
    });

    test("should show New Reminder button", async ({ page }) => {
      await page.goto("/reminders");
      await expect(page.getByRole("link", { name: "New Reminder" })).toBeVisible();
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
      await page.goto("/reminders/new");

      await page.locator("#title").fill("Doctor Appointment");
      await page.locator("#description").fill("Annual checkup with Dr. Smith");
      await page.locator("#start_datetime").fill("2026-04-15T10:00");
      await page.getByRole("button", { name: "Create Reminder" }).click();
      await expect(page).toHaveURL(/\/reminders/, { timeout: 10000 });
    });
  });
});
