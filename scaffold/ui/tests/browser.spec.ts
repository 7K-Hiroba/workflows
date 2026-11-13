import { expect, test } from '@playwright/test';

test('stable host mounts the declared health slot', async ({ page }) => {
  test.skip(!process.env.INARI_UI_URL, 'requires the pinned stable UI host supplied by compat-check');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(process.env.INARI_UI_URL!);
  await expect(page.locator('[data-inari-slot="health"]')).toBeVisible();
  expect(errors).toEqual([]);
});
