import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers/auth";

test.describe("Navigation & Layout", () => {
  test.describe("Unauthenticated access", () => {
    test("should redirect to login for protected pages", async ({ page }) => {
      await page.goto("/dashboard");
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    });

    test("should redirect to login when accessing members", async ({ page }) => {
      await page.goto("/members");
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    });
  });

  test.describe("Authenticated layout", () => {
    test.beforeEach(async ({ page }) => {
      await registerAndLogin(page, "e2e_nav_user");
    });

    test("should display sidebar navigation", async ({ page }) => {
      await expect(page.getByRole("link", { name: "Dashboard" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Family Members" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Providers" })).toBeVisible();
    });

    test("should display schedule section in sidebar", async ({ page }) => {
      await expect(page.getByRole("link", { name: "Reminders" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Notifications" })).toBeVisible();
    });

    test("should display admin section in sidebar", async ({ page }) => {
      await expect(page.getByRole("link", { name: "Settings" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Audit Log" })).toBeVisible();
    });

    test("should navigate to members page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "Family Members" }).click();
      await expect(page).toHaveURL(/\/members/);
    });

    test("should navigate to providers page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "Providers" }).click();
      await expect(page).toHaveURL(/\/providers/);
    });

    test("should navigate to reminders page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "Reminders" }).click();
      await expect(page).toHaveURL(/\/reminders/);
    });

    test("should navigate to notifications page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "Notifications" }).click();
      await expect(page).toHaveURL(/\/notifications/);
    });

    test("should display app name in sidebar", async ({ page }) => {
      await expect(
        page.locator("aside").getByRole("link", { name: /health tracker/i })
      ).toBeVisible();
    });

    test("should display header", async ({ page }) => {
      await expect(page.locator("header")).toBeVisible();
    });
  });
});
