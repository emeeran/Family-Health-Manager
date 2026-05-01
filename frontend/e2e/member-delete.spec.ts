import { test, expect } from "@playwright/test";

test.setTimeout(60000);

test("create, view, and delete a family member", async ({ page }) => {
  // 1. Login
  await page.goto("/login");
  await page.getByLabel("Username").fill("demo@example.com");
  await page.getByLabel("Password").fill("Admin@ass123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/(dashboard|members)/, { timeout: 10000 });

  // 2. Navigate to add member page
  await page.goto("/members/new");
  await expect(page.getByText("Add Family Member")).toBeVisible({ timeout: 10000 });

  // 3. Fill in the form
  await page.getByLabel("First Name").fill("Browser");
  await page.getByLabel("Last Name").fill("Test");
  await page.getByLabel("Date of Birth").fill("1995-03-20");

  // Select Gender: Male (shadcn Select)
  await page.locator('button:has-text("Select gender")').click();
  await page.locator('[role="option"]:has-text("Male")').first().click();

  // Select Relationship: Child (shadcn Select)
  await page.locator('button:has-text("Select relationship")').click();
  await page.locator('[role="option"]:has-text("Child")').first().click();

  // 4. Submit the form
  await page.getByRole("button", { name: /add member/i }).click();

  // 5. Verify redirect to members list
  await expect(page).toHaveURL(/\/members/, { timeout: 10000 });

  // 6. Navigate to members list and find "Browser Test"
  await page.goto("/members");
  const memberLink = page.locator("a", { hasText: "Browser Test" }).first();
  await expect(memberLink).toBeVisible({ timeout: 10000 });

  // 7. Click on the member to go to their dashboard
  await memberLink.click();
  await expect(page.getByText("Browser Test")).toBeVisible({ timeout: 10000 });

  // 8. Click the Delete button
  const deleteBtn = page.getByRole("button", { name: /delete/i }).first();
  await deleteBtn.click();

  // 9. Confirm the deletion in the dialog
  await expect(page.getByText("Are you sure you want to delete")).toBeVisible({ timeout: 5000 });
  // Click the destructive confirm button inside the dialog
  await page.locator('[role="dialog"] >> button:has-text("Delete")').last().click();

  // 10. Verify redirect back to /members list
  await expect(page).toHaveURL(/\/members/, { timeout: 10000 });

  // 11. Verify "Browser Test" no longer appears as a clickable card link
  //     (soft-delete sets is_active=false, member may still show as Inactive)
  await expect(page.locator("a", { hasText: "Browser Test" })).not.toBeVisible({ timeout: 5000 });
});
