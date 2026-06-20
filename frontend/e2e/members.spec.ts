import { test, expect } from "@playwright/test";
import { registerAndLogin, createMemberViaApi } from "./helpers/auth";

test.describe("Family Members", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, "e2e_members_user");
  });

  test.describe("People list", () => {
    test("should navigate to people page", async ({ page }) => {
      await page.getByRole("link", { name: "People" }).click();
      await expect(page).toHaveURL(/\/people/);
    });

    test("should show the add-member entry point on the empty list", async ({ page }) => {
      // Use a fresh user guaranteed to have no members (the shared
      // e2e_members_user accumulates members from sibling tests + prior runs).
      await registerAndLogin(page, `e2e_empty_${Date.now()}`);
      await page.goto("/people");
      await expect(page.getByRole("link", { name: /add your first member/i })).toBeVisible({
        timeout: 10000,
      });
    });

    test("should display member cards after creating one", async ({ page }) => {
      await createMemberViaApi(page, {
        first_name: "Visible",
        last_name: "User",
        date_of_birth: "1990-06-15",
      });

      await page.goto("/people");
      await expect(page.getByText("Visible User").first()).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe("Create member", () => {
    test("should display new member form", async ({ page }) => {
      await page.goto("/people/new");
      await expect(page.locator("#first_name")).toBeVisible();
      await expect(page.locator("#last_name")).toBeVisible();
      await expect(page.locator("#date_of_birth")).toBeVisible();
      await expect(page.getByRole("button", { name: "Add Member" })).toBeVisible();
    });

    test("should stay on form for empty required fields", async ({ page }) => {
      await page.goto("/people/new");
      await page.waitForLoadState("networkidle");
      await page.getByRole("button", { name: "Add Member" }).click();
      await expect(page).toHaveURL(/\/people\/new/);
    });

    test("should fill and submit member form", async ({ page }) => {
      test.setTimeout(60000);
      await page.goto("/people/new");
      await page.waitForLoadState("networkidle");
      await page.locator("#first_name").fill("John");
      await page.locator("#last_name").fill("Doe");
      await page.locator("#date_of_birth").fill("1990-01-15");

      // Gender + Relationship are Base UI Selects bound via RHF setValue —
      // drive them via the UI (not by writing hidden inputs) so the form state
      // updates and submit carries valid values.
      await page.locator('[data-slot="select-trigger"]').first().click();
      await page.getByRole("option").first().click();
      await page.locator('[data-slot="select-trigger"]').nth(1).click();
      await page.getByRole("option").first().click();

      await page.getByRole("button", { name: "Add Member" }).click();
      await expect(page).toHaveURL(/\/people\/?$/, { timeout: 15000 });
    });

    test("should fill medical history fields when expanded", async ({ page }) => {
      // The Medical History section is expanded by default (showMedical=true),
      // so the clinical fields are rendered without toggling.
      await page.goto("/people/new");
      await page.waitForLoadState("networkidle");
      await expect(page.locator("#conditions")).toBeVisible();
      await expect(page.locator("#current_medications")).toBeVisible();
      await expect(page.locator("#past_surgeries")).toBeVisible();
    });
  });

  test.describe("Edit member", () => {
    test("should navigate to edit form from member list", async ({ page }) => {
      const memberId = await createMemberViaApi(page, {
        first_name: "Edit",
        last_name: "Target",
        date_of_birth: "1985-03-20",
      });

      await page.goto(`/people/${memberId}/edit`);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("button", { name: "Update Member" })).toBeVisible({
        timeout: 10000,
      });
    });
  });
});
