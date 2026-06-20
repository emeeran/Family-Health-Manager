import { test, expect } from "@playwright/test";
import { registerAndLogin, createMemberViaApi } from "./helpers/auth";

test.setTimeout(60000);

test("create, view, and delete a family member", async ({ page }) => {
  await registerAndLogin(page, `e2e_delete_${Date.now()}`);

  // 1. Create a member via the API (UI form Selects are hard to drive in tests).
  const first = "Zippy";
  const last = "Deleteperson";
  const memberId = await createMemberViaApi(page, {
    first_name: first,
    last_name: last,
    date_of_birth: "1995-03-20",
  });
  expect(memberId).toBeTruthy();

  // 2. On the People list, the member card has a delete affordance.
  await page.goto("/people");
  await expect(page.getByText(`${first} ${last}`).first()).toBeVisible({ timeout: 10000 });

  // 3. Open the delete confirmation dialog from the card. The delete trigger
  // is a span[role="button"] with an explicit aria-label (a tooltip button
  // wraps it, so getByRole is ambiguous — target the span directly).
  await page.locator(`[aria-label="Delete ${first} ${last}"]`).click();
  await expect(page.getByText(/are you sure you want to delete this member/i)).toBeVisible();

  // 4. Confirm the deletion (destructive "Delete" button in the dialog).
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();

  // 5. Wait for the dialog to close, then re-load the list and confirm the
  //    member is gone (soft-delete + SWR revalidation).
  await expect(page.getByText(/are you sure you want to delete this member/i)).toHaveCount(0, {
    timeout: 10000,
  });
  await page.goto("/people");
  await expect(page.getByText(`${first} ${last}`)).toHaveCount(0, { timeout: 10000 });
});
