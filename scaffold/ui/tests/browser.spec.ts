import { expect, test } from '@playwright/test';

test('slot cluster-tab:health mounts in the stable host', async ({ page }) => {
  const baseURL = process.env.INARI_UI_URL;
  const remoteEntry = process.env.INARI_REMOTE_ENTRY;
  test.skip(!baseURL || !remoteEntry, 'requires the pinned stable UI host and OCI-built remote supplied by compat-check');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto(`${baseURL}/extensions`);
  await page.locator('#ext-name').fill('workflows-scaffold');
  await page.locator('#ext-entry').fill(remoteEntry!);
  await page.getByRole('button', { name: 'Add remote', exact: true }).click();
  await expect(page.locator('tr', { hasText: 'workflows-scaffold' }).getByText('healthy', { exact: true })).toBeVisible();

  await page.goto(`${baseURL}/clusters`);
  await page.locator('table a[href*="/clusters/"]').first().click();
  await page.getByRole('tab', { name: 'Health', exact: true }).click();
  await expect(page.locator('[data-inari-slot="health"]')).toBeVisible();
  expect(errors).toEqual([]);
});
