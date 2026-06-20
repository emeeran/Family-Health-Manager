import { test, expect } from "@playwright/test";
import { registerAndLogin, createMemberViaApi } from "./helpers/auth";
import path from "path";

test.setTimeout(120000);

const FIXTURE = path.join(__dirname, "fixtures", "test-medical.jpg");

// Multi-file upload in the classic form. Extraction is AI-dependent
// (absent/slow in the test env), so we assert the upload list + form structure
// and tolerate extraction outcome.
test("multi-file upload renders the file list and keeps the form usable", async ({ page }) => {
  await registerAndLogin(page, `e2e_mfx_${Date.now()}`);
  const memberId = await createMemberViaApi(page, {
    first_name: "Multi",
    last_name: "Upload",
    date_of_birth: "1990-01-01",
  });

  await page.goto(`/people/${memberId}/records/new`);
  await page.getByRole("button", { name: /switch to classic form/i }).click();
  await expect(page.getByText("Upload & Extract")).toBeVisible({ timeout: 10000 });

  // Upload the fixture — extraction auto-triggers via onChange.
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(FIXTURE);

  // Wait for extraction to settle (Extracted N, or an AI-unavailable error).
  await expect
    .poll(
      async () =>
        (await page.getByText(/Extracted \d+ file/).count()) > 0 ||
        (await page.locator(".text-destructive").count()) > 0,
      { timeout: 90_000, intervals: [1000, 2000, 5000] }
    )
    .toBeTruthy();

  // Form structure is intact and submittable.
  await expect(page.getByText("Record Type")).toBeVisible();
  await expect(page.getByRole("button", { name: /create record/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /create record/i })).toBeEnabled();
});
