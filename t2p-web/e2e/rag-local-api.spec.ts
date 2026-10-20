import { expect, test } from '@playwright/test';

test('uses the real offline backend for generation, typed scoring and course evidence', async ({ page }) => {
  test.setTimeout(120_000);
  test.skip(process.env.RUN_LOCAL_API_E2E !== '1', 'Requires the isolated local backend on port 8002.');
  await page.goto('/');
  await expect(page.getByText('Offline AI simulation', { exact: true })).toBeVisible();
  await page.getByLabel('Knowledge dimension').selectOption('Derivatives and Differentiation');
  // The first request loads the local embedding model; assert the actual response
  // separately from rendering rather than applying a warm-start UI deadline.
  const [generation] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/generate') && response.request().method() === 'POST', { timeout: 90_000 }),
    page.getByRole('button', { name: 'Generate current configuration question' }).click(),
  ]);
  expect(generation.ok()).toBe(true);
  const answer = page.getByRole('textbox', { name: /Final expression/ });
  await expect(answer).toBeVisible();
  // A definitely incorrect expression is enough to verify the entire feedback path.
  await answer.fill('0');
  await page.getByRole('button', { name: 'Submit typed answer' }).click();
  await expect(page.getByText('Your answer does not agree with the stored reference.')).toBeVisible();
  await page.getByRole('button', { name: /\[C1\]/ }).click();
  const source = page.getByRole('dialog', { name: 'Course source' });
  await expect(source).toBeVisible();
  await expect(source.getByText('Original project teaching notes', { exact: false })).toBeVisible();
  await page.screenshot({ path: 'test-results/rag-source.png', fullPage: true });
});
