import { expect, test } from '@playwright/test';
import {
  AUDIT_TIMEOUT_MS,
  DEFAULT_API_TIMEOUT_MS,
  GENERATION_TIMEOUT_MS,
  getApiErrorMessage,
} from '../src/lib/api';
import { aggregateMasteryDomains, getTopicChartLabel } from '../src/lib/progress';

const API_ORIGIN = 'http://127.0.0.1:8002';
const B_GRADE_TOPICS = {
  'Limits and Continuity': { mastery_score: 0.85, current_level: 3, completed_count: 5 },
  'Derivatives and Differentiation': { mastery_score: 0.94, current_level: 3, completed_count: 8 },
  'Integration and FTOC': { mastery_score: 0.85, current_level: 3, completed_count: 5 },
  'Multivariable Calculus': { mastery_score: 0.81, current_level: 2, completed_count: 4 },
  'Applications of Derivatives': { mastery_score: 0.91, current_level: 3, completed_count: 7 },
  'Indefinite Integrals': { mastery_score: 0.84, current_level: 3, completed_count: 5 },
  'Applications of Integration': { mastery_score: 0.82, current_level: 2, completed_count: 4 },
  'Multiple Integrals': { mastery_score: 0.76, current_level: 2, completed_count: 4 },
  'Vector Calculus': { mastery_score: 0.79, current_level: 2, completed_count: 3 },
  'Sequences and Series': { mastery_score: 0.85, current_level: 3, completed_count: 5 },
  'Differential Equations': { mastery_score: 0.81, current_level: 2, completed_count: 3 },
  'Techniques of Integration': { mastery_score: 0.83, current_level: 3, completed_count: 5 },
  'Parametric and Polar Curves': { mastery_score: 0.82, current_level: 2, completed_count: 4 },
};

test('aggregates thirteen topics into six unique academic domains', () => {
  const domains = aggregateMasteryDomains(Object.fromEntries(
    Object.entries(B_GRADE_TOPICS).map(([topic, progress]) => [topic, progress.mastery_score]),
  ));
  expect(domains.map((item) => [item.domain, item.mastery])).toEqual([
    ['Foundations', 85],
    ['Differential', 93],
    ['Integral', 84],
    ['Multivariable', 79],
    ['Series & Curves', 84],
    ['Diff. Equations', 81],
  ]);
  expect(new Set(domains.map((item) => item.domain)).size).toBe(6);
  expect(getTopicChartLabel('Applications of Derivatives')).toBe('Derivative Apps');
  expect(getTopicChartLabel('Applications of Integration')).toBe('Integral Apps');
});

test('uses a dedicated timeout for long-running AI generation', () => {
  expect(DEFAULT_API_TIMEOUT_MS).toBe(30_000);
  expect(GENERATION_TIMEOUT_MS).toBe(180_000);
  expect(AUDIT_TIMEOUT_MS).toBe(180_000);
  expect(GENERATION_TIMEOUT_MS).toBeGreaterThan(74_051);
  expect(getApiErrorMessage(
    { isAxiosError: true, code: 'ECONNABORTED' },
    'fallback',
    'AI generation timed out.',
  )).toBe('AI generation timed out.');
});

test('registers, generates, audits, and opens the authenticated dashboard', async ({ page }) => {
  let recorded = false;

  await page.route(`${API_ORIGIN}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const authorization = request.headers().authorization;

    if (path === '/topics') {
      return route.fulfill({
        json: { success: true, topics: ['Derivatives', 'Integrals'] },
      });
    }
    if (path === '/capabilities') {
      return route.fulfill({
        json: {
          success: true,
          grading: { provider: 'deepseek', model: 'deepseek-v4-pro', input: 'text' },
          vision_ocr: { configured: true, provider: 'test-vision', model: 'vision-test' },
        },
      });
    }
    if (path === '/auth/register') {
      return route.fulfill({
        status: 201,
        json: {
          success: true,
          access_token: 'e2e-session-token',
          token_type: 'bearer',
          expires_at: '2099-01-01T00:00:00Z',
          user: { user_id: 'e2e_student', role: 'student' },
        },
      });
    }
    if (path === '/auth/me') {
      expect(authorization).toBe('Bearer e2e-session-token');
      return route.fulfill({
        json: {
          success: true,
          user: { user_id: 'e2e_student', role: 'student' },
          expires_at: '2099-01-01T00:00:00Z',
        },
      });
    }
    if (path === '/generate') {
      expect(authorization).toBe('Bearer e2e-session-token');
      return route.fulfill({
        json: {
          success: true,
          data: [
            {
              id: 'E2E-DERIV-1',
              problem_id: 'E2E-DERIV-1',
              topic: 'Derivatives',
              sub_topic: 'Power Rule',
              problem_statement: 'What is the derivative of $x^2$?',
              question_type: 'mcq',
              difficulty: 2,
              options: { A: '$2x$', B: '$x$', C: '$x^2$', D: '$2$' },
              answer: 'A',
              scaffolding: [{ step: 1, hint: 'Use the power rule.' }],
            },
          ],
        },
      });
    }
    if (path === '/audit') {
      expect(authorization).toBe('Bearer e2e-session-token');
      const submission = route.request().postDataJSON();
      expect(submission.selected_option).toBe('A');
      expect(submission.student_work_image).toBeUndefined();
      await new Promise((resolve) => setTimeout(resolve, 300));
      return route.fulfill({
        json: {
          success: true,
          submission_id: 'sub_e2e',
          is_correct: true,
          logic_alignment_score: 100,
          error_analysis: 'No mathematical error detected.',
          tutor_feedback: 'Excellent derivative reasoning.',
          next_hint: 'Continue with the chain rule.',
          ocr_text: 'A',
        },
      });
    }
    if (path === '/user/record') {
      expect(authorization).toBe('Bearer e2e-session-token');
      recorded = true;
      return route.fulfill({ json: { success: true } });
    }
    if (path === '/user/progress/e2e_student') {
      expect(authorization).toBe('Bearer e2e-session-token');
      return route.fulfill({
        json: {
          success: true,
          user_id: 'e2e_student',
          total_minutes: 900,
          topics_status: B_GRADE_TOPICS,
        },
      });
    }
    return route.fulfill({ status: 404, json: { detail: `Unhandled ${path}` } });
  });

  await page.goto('/');
  await expect(page).toHaveTitle('Calculus Atelier');
  await expect(page.getByText('Calculus Atelier', { exact: true }).first()).toBeVisible();
  const workspaceNavigation = page.getByRole('navigation', { name: 'Primary workspace navigation' });
  await expect(page.getByRole('heading', { name: 'Problem Workspace' })).toBeVisible();
  await workspaceNavigation.getByRole('button', { name: 'Agent Laboratory' }).click();
  await expect(page.getByRole('heading', { name: 'Agent Laboratory', exact: true })).toBeVisible();
  await workspaceNavigation.getByRole('button', { name: 'Problem Studio' }).click();

  const topicSelect = page.getByLabel('Knowledge dimension');
  await expect(topicSelect).toHaveValue('Derivatives');
  await topicSelect.selectOption('Integrals');
  await expect(topicSelect).toHaveValue('Integrals');
  await topicSelect.selectOption('Derivatives');

  const generateButton = page.getByRole('button', { name: 'Generate current configuration question' });
  await expect(generateButton).toHaveCSS('color', 'rgb(255, 255, 255)');

  await page.getByLabel('User ID').fill('e2e_student');
  await page.getByLabel('Password').fill('StrongPass!123');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Register' }).click();
  await expect(page.getByText('e2e_student')).toBeVisible();

  await page.getByRole('button', { name: 'MCQ', exact: true }).click();
  await generateButton.click();
  await expect(page.getByText('What is the derivative of')).toBeVisible();

  const selectedOption = page.getByRole('button', { name: 'Option A: $2x$' });
  await selectedOption.click();
  await expect(selectedOption).toHaveAttribute('aria-pressed', 'true');
  await expect(selectedOption).toHaveClass(/is-selected/);
  await expect(selectedOption).toHaveCSS('background-color', 'rgb(24, 49, 83)');
  await expect(selectedOption.getByText('Selected', { exact: true })).toBeVisible();
  await expect(page.getByText('Excellent derivative reasoning.')).toBeVisible();
  await expect(selectedOption).toHaveAttribute('aria-pressed', 'true');
  await expect(selectedOption).toHaveCSS('background-color', 'rgb(24, 49, 83)');
  await expect.poll(() => recorded).toBe(true);

  await page.getByRole('link', { name: 'Progress Report' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText('Calculus Atelier', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Academic Progress Report' })).toBeVisible();
  await expect(page.getByText('Derivatives and Differentiation', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('84%', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('B', { exact: true })).toBeVisible();
  await expect(page.getByText('Proficient · 15 h documented study', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Convert procedural strength into balanced mastery.' })).toBeVisible();
  await expect(page.getByText('6-domain view · 13 topics', { exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: /Aggregated calculus domain mastery/ })).toBeVisible();
  await expect(page.locator('.mastery-domain-key > div')).toHaveCount(6);
  const radarAxisLabels = page.locator('.mastery-radar .recharts-polar-angle-axis text');
  await expect(radarAxisLabels).toHaveCount(6);
  expect(await radarAxisLabels.allTextContents()).toEqual([
    'Foundations',
    'Differential',
    'Integral',
    'Multivariable',
    'Series & Curves',
    'Diff. Equations',
  ]);
  await expect(page.getByText('Derivative Apps', { exact: true })).toBeVisible();
  await expect(page.getByText('Integral Apps', { exact: true })).toBeVisible();
});

test('keeps the academic workspace within a mobile viewport', async ({ page }) => {
  await page.route(`${API_ORIGIN}/topics`, (route) => route.fulfill({
    json: { success: true, topics: ['Derivatives', 'Integrals'] },
  }));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Problem Workspace' })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    viewportWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
});
