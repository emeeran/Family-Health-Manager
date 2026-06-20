import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers/auth";

test.setTimeout(90000);

async function openDataTab(page: import("@playwright/test").Page) {
  // The Settings page reads the active tab from ?tab=, so navigate directly
  // rather than driving the custom (non-role="tab") tab buttons.
  await page.goto("/settings?tab=data");
  await expect(page.getByText("Data Management")).toBeVisible({ timeout: 10000 });
}

test("backup export downloads a ZIP file", async ({ page }) => {
  await registerAndLogin(page, `e2e_backup_${Date.now()}`);

  await openDataTab(page);

  const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
  await page.getByRole("button", { name: "Export Backup" }).click();
  const download = await downloadPromise;

  const path = await download.path();
  expect(path).toBeTruthy();
});

test("backup import validates and shows review", async ({ page }) => {
  await registerAndLogin(page, `e2e_import_${Date.now()}`);

  // First export a backup from this household.
  await openDataTab(page);
  const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
  await page.getByRole("button", { name: "Export Backup" }).click();
  const download = await downloadPromise;
  const downloadPath = `/tmp/test-backup-e2e-${Date.now()}.zip`;
  await download.saveAs(downloadPath);

  // Now test the import flow.
  await openDataTab(page);
  const fileInput = page.locator('input[type="file"][accept=".zip"]');
  await fileInput.setInputFiles(downloadPath);

  // Wait for validation and review UI.
  await expect(page.getByText("Import mode")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/member\(s\)/)).toBeVisible();

  // Merge mode is offered.
  await expect(page.getByRole("button", { name: /merge/i }).first()).toBeVisible();

  // Cancel returns to idle state.
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("button", { name: "Export Backup" })).toBeVisible();
});
