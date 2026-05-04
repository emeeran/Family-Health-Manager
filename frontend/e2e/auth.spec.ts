import { test, expect } from "@playwright/test";
import { TEST_PASSWORD } from "./helpers/auth";

const API_BASE = "http://localhost:3000/api/v1";
const TEST_USER = "e2e_auth_user";

test.describe("Authentication", () => {
  test.describe("Login", () => {
    // Register user via API once for login tests
    test.beforeAll(async ({ browser }) => {
      const ctx = await browser.newContext();
      await ctx.request.post(`${API_BASE}/auth/register`, {
        data: { username: TEST_USER, password: TEST_PASSWORD },
        failOnStatusCode: false,
      });
      await ctx.close();
    });

    test("should display login form", async ({ page }) => {
      await page.goto("/login");
      await expect(page.locator("#username")).toBeVisible();
      await expect(page.locator("#password")).toBeVisible();
      await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
    });

    test("should navigate to register page", async ({ page }) => {
      await page.goto("/login");
      await page.getByRole("link", { name: "Register" }).click();
      await expect(page).toHaveURL("/register");
    });

    test("should stay on login for empty fields", async ({ page }) => {
      await page.goto("/login");
      await page.waitForLoadState("networkidle");
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page).toHaveURL(/\/login/);
      await expect(page.getByText(/must be at least/i).first()).toBeVisible();
    });

    test("should show error for invalid credentials", async ({ page }) => {
      await page.goto("/login");
      await page.waitForLoadState("networkidle");
      await page.locator("#username").fill("wronguser");
      await page.locator("#password").fill("wrongpassword1!");
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page.getByRole("alert")).toBeVisible({ timeout: 15000 });
    });

    test("should login successfully with valid credentials", async ({ page }) => {
      await page.goto("/login");
      await page.waitForLoadState("networkidle");
      await page.locator("#username").fill(TEST_USER);
      await page.locator("#password").fill(TEST_PASSWORD);
      await page.getByRole("button", { name: "Sign In" }).click();
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 20000 });
    });
  });

  test.describe("Register", () => {
    test("should display registration form", async ({ page }) => {
      await page.goto("/register");
      await expect(page.locator("#username")).toBeVisible();
      await expect(page.locator("#password")).toBeVisible();
      await expect(page.locator("#confirmPassword")).toBeVisible();
      await expect(page.getByRole("button", { name: "Create Account" })).toBeVisible();
    });

    test("should navigate to login page", async ({ page }) => {
      await page.goto("/register");
      await page.getByRole("link", { name: "Sign in" }).click();
      await expect(page).toHaveURL("/login");
    });

    test("should show password requirement indicators", async ({ page }) => {
      await page.goto("/register");
      await expect(page.getByText(/8\+ characters/)).toBeVisible();
      await expect(page.getByText("Uppercase letter")).toBeVisible();
      await expect(page.getByText("Digit")).toBeVisible();
      await expect(page.getByText("Special character")).toBeVisible();
    });

    test("should update password indicators as user types", async ({ page }) => {
      await page.goto("/register");
      await page.waitForLoadState("networkidle");
      await page.locator("#password").type("TestPass1!");
      await expect(page.locator(".text-green-600").filter({ hasText: "8+" })).toBeVisible();
      await expect(page.locator(".text-green-600").filter({ hasText: "Uppercase" })).toBeVisible();
      await expect(page.locator(".text-green-600").filter({ hasText: "Digit" })).toBeVisible();
      await expect(page.locator(".text-green-600").filter({ hasText: "Special" })).toBeVisible();
    });

    test("should show error for mismatched passwords", async ({ page }) => {
      await page.goto("/register");
      await page.waitForLoadState("networkidle");
      await page.locator("#username").fill("mismatchuser");
      await page.locator("#password").fill("TestPass1!");
      await page.locator("#confirmPassword").fill("DifferentPass1!");
      await page.getByRole("button", { name: "Create Account" }).click();
      await expect(page.getByText("Passwords do not match")).toBeVisible();
    });

    test("should register successfully with valid data", async ({ page }) => {
      const uniqueName = `user_${Date.now()}`;
      await page.goto("/register");
      await page.waitForLoadState("networkidle");
      await page.locator("#username").fill(uniqueName);
      await page.locator("#password").fill("TestPass1!");
      await page.locator("#confirmPassword").fill("TestPass1!");
      await page.getByRole("button", { name: "Create Account" }).click();
      await expect(page).toHaveURL(/\/(dashboard|login)/, { timeout: 15000 });
    });
  });
});
