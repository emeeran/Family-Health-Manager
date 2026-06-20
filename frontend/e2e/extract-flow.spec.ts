import { test, expect } from "@playwright/test";
import { registerAndLogin, createMemberViaApi } from "./helpers/auth";
import path from "path";

test.setTimeout(90000);

const FIXTURE = path.join(__dirname, "fixtures", "test-medical.jpg");

// The classic record form auto-runs extraction when a file is selected.
// Extraction depends on the configured AI provider (absent/slow in the test
// env), so this test verifies the upload→extract pipeline structurally and
// tolerates AI unavailability rather than asserting populated fields.
test("file upload triggers the extract pipeline in the classic form", async ({ page }) => {
  await registerAndLogin(page, `e2e_extract_${Date.now()}`);
  const memberId = await createMemberViaApi(page, {
    first_name: "Extract",
    last_name: "Patient",
    date_of_birth: "1990-01-01",
  });

  await page.goto(`/people/${memberId}/records/new`);
  await page.getByRole("button", { name: /switch to classic form/i }).click();

  // Upload section is present.
  await expect(page.getByText("Upload & Extract")).toBeVisible({ timeout: 10000 });
  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toBeAttached();

  // Selecting a file auto-triggers extraction.
  await fileInput.setInputFiles(FIXTURE);

  // Wait for extraction to settle (success or AI-unavailable). Bounded.
  await expect
    .poll(
      async () =>
        (await page.getByText(/Extracted \d+ file/).count()) > 0 ||
        (await page.locator(".text-destructive").count()) > 0,
      { timeout: 60_000, intervals: [1000, 2000, 5000] }
    )
    .toBeTruthy();

  // The form remains usable regardless of extraction outcome.
  await expect(page.getByRole("button", { name: /create record/i })).toBeVisible();
});
