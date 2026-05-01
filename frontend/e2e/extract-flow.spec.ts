import { test, expect } from "@playwright/test";

test.setTimeout(90000);

test("extraction auto-populates form fields with JPEG", async ({ page }) => {
  // 1. Login
  await page.goto("/login");
  await page.getByLabel("Username").fill("demo@example.com");
  await page.getByLabel("Password").fill("Admin@ass123");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/(dashboard|members)/, { timeout: 10000 });

  // 2. Navigate to members page
  await page.goto("/members");
  const memberLink = page
    .locator('a[href^="/members/"]')
    .filter({ hasNotText: /add|new/i })
    .first();
  const href = await memberLink.getAttribute("href");
  const memberId = href?.match(/\/members\/([^/]+)/)?.[1];
  if (!memberId || memberId === "new") throw new Error("No member found");

  // 3. Go to new record page
  await page.goto(`/members/${memberId}/records/new`);
  await expect(page.getByText("Upload Medical Document")).toBeVisible({ timeout: 10000 });

  // 4. Upload the test JPEG
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles("/tmp/test-medical.jpg");

  // 5. Click Extract Data
  const extractBtn = page.getByRole("button", { name: /extract data/i });
  await expect(extractBtn).toBeEnabled({ timeout: 3000 });
  await extractBtn.click();

  // 6. Wait for extraction to complete
  await page.waitForFunction(
    () => {
      const btns = Array.from(document.querySelectorAll("button"));
      const eb = btns.find((b) => /extract/i.test(b.textContent || ""));
      return eb && !/extracting/i.test(eb.textContent || "");
    },
    { timeout: 60000 }
  );

  // 7. Verify form fields are populated
  const clinicalData = await page.locator("#clinical_data").inputValue();
  const diagnosis = await page.locator("#diagnosis").inputValue();

  console.log("Clinical data:", clinicalData?.substring(0, 100));
  console.log("Diagnosis:", diagnosis);

  expect(clinicalData.length).toBeGreaterThan(0);
});
