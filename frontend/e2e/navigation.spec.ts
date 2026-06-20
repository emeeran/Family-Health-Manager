import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers/auth";

test.describe("Navigation & Layout", () => {
  test.describe("Unauthenticated access", () => {
    test("should redirect to login for protected pages", async ({ page }) => {
      await page.goto("/people");
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    });

    test("should redirect to login when accessing providers", async ({ page }) => {
      await page.goto("/providers");
      await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    });
  });

  test.describe("Authenticated layout", () => {
    test.beforeEach(async ({ page }) => {
      await registerAndLogin(page, "e2e_nav_user");
    });

    test("should display sidebar navigation", async ({ page }) => {
      await expect(page.getByRole("link", { name: "Home" })).toBeVisible();
      await expect(page.getByRole("link", { name: "People" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Providers" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Records" })).toBeVisible();
      await expect(page.getByRole("link", { name: "AI Tools" })).toBeVisible();
    });

    test("should navigate to people page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "People" }).click();
      await expect(page).toHaveURL(/\/people/);
    });

    test("should navigate to providers page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "Providers" }).click();
      await expect(page).toHaveURL(/\/providers/);
    });

    test("should navigate to records page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "Records" }).click();
      await expect(page).toHaveURL(/\/records/);
    });

    test("should navigate to AI tools page via sidebar", async ({ page }) => {
      await page.getByRole("link", { name: "AI Tools" }).click();
      await expect(page).toHaveURL(/\/ai-tools/);
    });

    test("should display app name in sidebar", async ({ page }) => {
      await expect(page.locator("aside").getByText("DAWNSTAR")).toBeVisible();
    });

    test("should display header", async ({ page }) => {
      await expect(page.locator("header")).toBeVisible();
    });
  });
});
