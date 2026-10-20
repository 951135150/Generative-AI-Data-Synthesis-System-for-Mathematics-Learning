import { expect, test } from '@playwright/test';

const API = 'http://127.0.0.1:8002';
const sourceID = 'browser-notes';
const chunk = { id: `${sourceID}-1`, title: 'Chain rule', topic: 'Derivatives and Differentiation', section: '1',
  text: 'Differentiate the outer function and multiply by the inner derivative.', source_id: sourceID,
  source_title: 'Browser course notes', source_version: '1' };

test('administrator previews, saves, publishes and withdraws a course source', async ({ page }) => {
  let status = '';
  const hash = 'a'.repeat(64);
  const source = () => ({ source_id: sourceID, title: 'Browser course notes', version: '1', status,
    source_hash: hash, chunk_count: 1, provenance: 'Original browser-test material', license: 'CC0-1.0' });
  const document = () => ({ ...source(), chunks: [chunk] });
  await page.addInitScript(() => { sessionStorage.setItem('t2p_access_token', 'course-admin-test-token'); });
  await page.route(`${API}/**`, async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/auth/me') return route.fulfill({ json: { success: true, user: { user_id: 'course_admin', role: 'admin' } } });
    if (path === '/knowledge/catalog') return route.fulfill({ json: {
      success: true, sources: status === 'published' ? [source()] : [], chunks: status === 'published' ? [chunk] : [],
    } });
    if (path === '/knowledge/manage/sources') return route.fulfill({ json: { success: true, sources: status ? [source()] : [] } });
    if (path === `/knowledge/manage/sources/${sourceID}`) return route.fulfill({ json: { success: true, document: document(), source_hash: hash } });
    if (path === '/knowledge/manage/preview') return route.fulfill({ json: {
      success: true, document: { ...document(), status: 'draft' }, existing_hash: null, preview_hash: hash,
    } });
    if (path === '/knowledge/manage/save') {
      expect(route.request().postDataJSON().publish).toBe(false);
      status = 'draft';
      return route.fulfill({ json: { success: true, status, source_hash: hash } });
    }
    if (path.endsWith('/status')) {
      const request = route.request().postDataJSON();
      expect(request.expected_hash).toBe(hash);
      if (request.status === 'published') expect(request.review_confirmed).toBe(true);
      status = request.status;
      return route.fulfill({ json: { success: true, status, source_hash: hash } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unhandled ${path}` } });
  });
  await page.goto('/knowledge');
  await expect(page.getByRole('heading', { name: 'Review before publication.' })).toBeVisible();
  await page.getByLabel('Source ID', { exact: true }).fill(sourceID);
  await page.getByLabel('Source title', { exact: true }).fill('Browser course notes');
  await page.getByLabel('Curriculum topic', { exact: true }).fill('Derivatives and Differentiation');
  await page.getByLabel('Author and provenance', { exact: true }).fill('Original browser-test material');
  await page.getByLabel('Permission or license', { exact: true }).fill('CC0-1.0');
  await page.getByLabel('Source text', { exact: true }).fill('# Chain rule\nDifferentiate the outer function.');
  await page.getByRole('button', { name: 'Preview source', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Import preview' })).toBeVisible();
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByText('Draft saved.', { exact: false })).toBeVisible();
  const publish = page.getByRole('button', { name: 'Publish reviewed source', exact: true });
  await expect(publish).toBeDisabled();
  await page.getByRole('button', { name: 'Review source', exact: true }).click();
  await page.getByRole('checkbox', { name: "I reviewed this source's rights, mathematics and extracted formulas." }).check();
  await publish.click();
  await expect(page.getByRole('region', { name: 'Course passages' }).getByRole('heading', { name: 'Chain rule' })).toBeVisible();
  await page.getByRole('button', { name: 'Withdraw', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Course passages' }).getByText('No matching published course passage was found.', { exact: false })).toBeVisible();
  await expect(page.getByText('Source withdrawn.', { exact: false })).toBeVisible();
});

test('learners browse and search notes without course publishing controls', async ({ page }) => {
  await page.route(`${API}/**`, async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.includes('/manage/')) throw new Error('Learners must not request administration data.');
    if (path === '/knowledge/catalog') return route.fulfill({ json: {
      success: true, sources: [{ source_id: sourceID, title: 'Browser course notes', version: '1', provenance: 'Original notes', license: 'CC0-1.0' }], chunks: [chunk],
    } });
    if (path === '/knowledge/search') return route.fulfill({ json: { success: true, data: { status: 'retrieved', evidence: [chunk] } } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('/knowledge');
  await expect(page.getByRole('heading', { name: 'Chain rule' })).toBeVisible();
  await page.screenshot({ path: 'test-results/course-library-desktop.png', fullPage: true });
  await expect(page.getByRole('region', { name: 'Course administration' })).toHaveCount(0);
  await page.getByLabel('Search course notes', { exact: true }).fill('chain rule');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Chain rule' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(widths[0]).toBeLessThanOrEqual(widths[1]);
  await page.screenshot({ path: 'test-results/course-library-mobile.png', fullPage: true });
});
