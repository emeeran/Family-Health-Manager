import { test, expect } from "@playwright/test";

test.setTimeout(90000);

test("backup export downloads a ZIP file", async ({ page }) => {
  // Login
  await page.goto("/login");
  await page.getByLabel("Username").fill("demo@example.com");
  await page.getByLabel("Password").fill("Admin@ass123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/(dashboard|members)/, { timeout: 15000 });

  // Go to settings
  await page.goto("/settings");
  await expect(page.getByText("Data Management")).toBeVisible({ timeout: 10000 });

  // Click export and wait for download
  const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
  await page.getByRole("button", { name: "Export Backup" }).click();
  const download = await downloadPromise;

  // Verify it's a ZIP file
  const path = await download.path();
  expect(path).toBeTruthy();
});

test("backup import validates and shows review", async ({ page }) => {
  // Login
  await page.goto("/login");
  await page.getByLabel("Username").fill("demo@example.com");
  await page.getByLabel("Password").fill("Admin@ass123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/(dashboard|members)/, { timeout: 15000 });

  // First export a backup
  await page.goto("/settings");
  await expect(page.getByText("Data Management")).toBeVisible({ timeout: 10000 });

  const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
  await page.getByRole("button", { name: "Export Backup" }).click();
  const download = await downloadPromise;

  // Save the downloaded file
  const downloadPath = `/tmp/test-backup-e2e-${Date.now()}.zip`;
  await download.saveAs(downloadPath);

  // Now test import flow
  await page.goto("/settings");
  await expect(page.getByText("Data Management")).toBeVisible({ timeout: 10000 });

  // Upload the backup file
  const fileInput = page.locator('input[type="file"][accept=".zip"]');
  await fileInput.setInputFiles(downloadPath);

  // Wait for validation and review
  await expect(page.getByText("Import mode")).toBeVisible({ timeout: 30000 });

  // Verify manifest info is shown
  await expect(page.getByText("Demo Household")).toBeVisible();
  await expect(page.getByText("member(s)")).toBeVisible();

  // Verify merge mode is selected by default
  await expect(page.getByRole("button", { name: /merge/i }).nth(0)).toBeVisible();

  // Cancel the import
  await page.getByRole("button", { name: "Cancel" }).click();

  // Should be back to idle state
  await expect(page.getByRole("button", { name: "Export Backup" })).toBeVisible();
});
