import { expect, test } from "@playwright/test";

test("two conversations survive a reload", async ({ page }) => {
  await page.goto("/");
  const items = page.locator(".ant-conversations-item");
  const before = await items.count();
  await page.getByRole("button", { name: "New chat" }).click();
  await expect(items).toHaveCount(before + 1);
  await page.getByRole("button", { name: "New chat" }).click();
  await expect(items).toHaveCount(before + 2);
  const open = page.url();
  await page.reload();
  await expect(items).toHaveCount(before + 2);
  await items.nth(1).click();
  await expect(page).toHaveURL(/\/c\//);
  await expect(page).not.toHaveURL(open);
});

test("a phone search keeps its cards after reload", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Ask for something in the catalog").fill("a phone under 500");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Galaxy Budget" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Galaxy Budget" })).toBeVisible();
});

test("assistant text arrives with the cards", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Ask for something in the catalog").fill("a phone under 500");
  await page.keyboard.press("Enter");
  await expect(page.locator(".assistant-text")).toContainText("Galaxy Budget");
  await expect(page.getByTestId("product-card").first()).toBeVisible();
});

test("a flight shows no cards", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Ask for something in the catalog").fill("a flight to Tokyo");
  await page.keyboard.press("Enter");
  await expect(page.locator(".assistant-text")).toContainText(/flight/i);
  await expect(page.getByTestId("product-card")).toHaveCount(0);
});

test("something cheap and cool asks a catalog question", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Ask for something in the catalog").fill("something cheap and cool");
  await page.keyboard.press("Enter");
  await expect(page.locator(".assistant-text")).toContainText(/what/i);
  await expect(page.locator(".assistant-text")).toContainText(/beauty|smartphone|laptop|home decoration/i);
});

test("the header opens the guide", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "How it works" }).click();
  await expect(page.getByText("The graph is compiled once")).toBeVisible();
  await expect(page.getByTestId("diagram-request")).toBeVisible();
  await expect(page.getByTestId("diagram-turn")).toBeVisible();
  await expect(page.getByTestId("diagram-freshness")).toBeVisible();
});
