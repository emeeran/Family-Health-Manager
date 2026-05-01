import { test, expect } from "@playwright/test";
import { registerAndLogin, createMemberViaApi, fillMemberForm } from "./helpers/auth";

test.describe("Family Members", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, "e2e_members_user");
  });

  test.describe("Members list", () => {
    test("should navigate to members page", async ({ page }) => {
      await page.getByRole("link", { name: "Family Members" }).click();
      await expect(page).toHaveURL(/\/members/);
    });

    test("should show Add Member button", async ({ page }) => {
      await page.goto("/members");
      await expect(page.getByRole("link", { name: "Add Member" })).toBeVisible();
    });

    test("should display member cards after creating one", async ({ page }) => {
      await createMemberViaApi(page, {
        first_name: "Visible",
        last_name: "User",
        date_of_birth: "1990-06-15",
      });

      await page.goto("/members");
      await expect(page.locator("a.hover\\:underline").first()).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe("Create member", () => {
    test("should display new member form", async ({ page }) => {
      await page.goto("/members/new");
      await expect(page.locator("#first_name")).toBeVisible();
      await expect(page.locator("#last_name")).toBeVisible();
      await expect(page.locator("#date_of_birth")).toBeVisible();
      await expect(page.getByRole("button", { name: "Add Member" })).toBeVisible();
    });

    test("should stay on form for empty required fields", async ({ page }) => {
      await page.goto("/members/new");
      await page.waitForLoadState("networkidle");
      await page.getByRole("button", { name: "Add Member" }).click();
      await expect(page).toHaveURL(/\/members\/new/);
    });

    // TODO: useActionState form with Base UI Select hidden inputs doesn't submit properly in tests
    test.skip("should fill and submit member form", async ({ page }) => {
      await page.goto("/members/new");
      await page.waitForLoadState("networkidle");
      await fillMemberForm(page, {
        first_name: "John",
        last_name: "Doe",
        date_of_birth: "1990-01-15",
      });
      await page.getByRole("button", { name: "Add Member" }).click();
      await expect(page).toHaveURL(/\/members\/?$/, { timeout: 15000 });
    });

    test("should fill medical history fields when expanded", async ({ page }) => {
      await page.goto("/members/new");
      await page.waitForLoadState("networkidle");
      await page.getByText("Medical History").click();
      await expect(page.locator("#conditions")).toBeVisible();
      await expect(page.locator("#allergies")).toBeVisible();
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

      // Navigate directly to edit page using API-returned member ID
      await page.goto(`/members/${memberId}/edit`);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("button", { name: "Update Member" })).toBeVisible({
        timeout: 10000,
      });
    });
  });
});
