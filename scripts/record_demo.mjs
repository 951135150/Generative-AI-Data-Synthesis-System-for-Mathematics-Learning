// Real browser acceptance and recording. No route interception or mocked API responses.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const folder = path.resolve(process.argv[2] || path.join(root, '.runtime/demo/acceptance_20261020'));
const rehearsal = process.argv.includes('--rehearsal');
if (!folder.startsWith(path.join(root, '.runtime', 'demo') + path.sep)) throw new Error('Use an isolated demo folder.');
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(root, '.runtime/playwright');
const require = createRequire(path.join(root, 't2p-web/package.json'));
const { chromium, request, expect } = require('@playwright/test');
const config = JSON.parse(await fs.readFile(path.join(folder, 'private_config.json'), 'utf8'));
const voices = JSON.parse(await fs.readFile(path.join(folder, 'voice/manifest.json'), 'utf8'));
const narrationFile = process.env.DEMO_NARRATION || 'data/evaluation/demo_narration.json';
const narration = JSON.parse(await fs.readFile(path.resolve(root, narrationFile), 'utf8'));
const output = path.join(root, 'reports/demo', path.basename(folder));
await fs.mkdir(path.join(output, 'screens'), { recursive: true });
const base = process.env.DEMO_WEB_URL || 'http://127.0.0.1:3103';
const apiBase = process.env.DEMO_API_URL || 'http://127.0.0.1:8003';
const http = await request.newContext({ timeout: 120_000 });
async function getJSON(url) { const r = await http.get(url); expect(r.ok()).toBeTruthy(); return r.json(); }
const health = await getJSON(apiBase + '/');
// Warm both actual services before recording.
await getJSON(apiBase + '/knowledge/search?query=chain%20rule');
await http.get(base + '/'); await http.get(base + '/dashboard'); await http.get(base + '/knowledge');
const caps = await getJSON(apiBase + '/capabilities');
expect(caps.ai_mode).toBe('simulation'); expect(caps.external_calls_enabled).toBe(false);
const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--disable-translate'] });
const context = await browser.newContext({ viewport: { width: 1600, height: 800 }, deviceScaleFactor: 1,
  reducedMotion: 'reduce', locale: 'en-US',
  ...(rehearsal ? {} : { recordVideo: { dir: path.join(folder, 'video'), size: { width: 1600, height: 800 } } }),
});
await context.addInitScript(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style');
    style.textContent = 'nextjs-portal{display:none!important}.demo-pointer{position:fixed;width:19px;height:19px;border:2px solid #af8138;background:#af813833;border-radius:50%;z-index:2147483646;pointer-events:none;left:-80px;top:-80px;transform:translate(-50%,-50%)}';
    document.head.append(style);
    const pointer = document.createElement('div'); pointer.className = 'demo-pointer'; document.body.append(pointer);
    document.addEventListener('mousemove', e => { pointer.style.left = e.clientX + 'px'; pointer.style.top = e.clientY + 'px'; });
  });
});
const page = await context.newPage();
const criticalErrors = [], failedRequests = [], checks = {}, timeline = [];
page.on('pageerror', error => criticalErrors.push(error.message));
page.on('requestfailed', r => { if (r.url().startsWith(apiBase) && r.failure()?.errorText !== 'net::ERR_ABORTED') failedRequests.push({ url: new URL(r.url()).pathname, error: r.failure()?.errorText }); });
page.on('dialog', dialog => dialog.accept());
const start = Date.now();
let beforeCount, afterCount, question, wrongOption, token;
const elapsed = () => (Date.now() - start) / 1000;
async function click(locator) {
  await locator.scrollIntoViewIfNeeded(); const b = await locator.boundingBox();
  if (b) await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: rehearsal ? 1 : 18 });
  await locator.click();
}
async function apiProgress() {
  const r = await http.get(apiBase + '/user/progress/' + config.user_id, { headers: { Authorization: 'Bearer ' + token } });
  expect(r.ok()).toBeTruthy(); return r.json();
}
const count = progress => Object.values(progress.topics_status).reduce((sum, row) => sum + row.completed_count, 0);
async function generate(kind) {
  await click(page.getByRole('button', { name: kind === 'mcq' ? 'MCQ' : 'Calc', exact: true }));
  const waiting = page.waitForResponse(r => r.url() === apiBase + '/generate' && r.request().method() === 'POST', { timeout: 120_000 });
  await click(page.getByRole('button', { name: 'Generate current configuration question' }));
  const r = await waiting; expect(r.ok()).toBeTruthy(); const result = await r.json();
  question = result.data[0];
  expect(question.topic).toBe('Derivatives and Differentiation'); expect(question.question_type).toBe(kind);
  expect(question.answer).toBeUndefined(); expect(question.expected_expression).toBeUndefined();
  return question;
}
async function scene(id, action) {
  const script = narration.scenes.find(s => s.id === id);
  const begin = elapsed();
  await action();
  if (!rehearsal) {
    const hold = Math.max(0, voices[id].duration + 2.2 - (elapsed() - begin));
    if (hold) await page.waitForTimeout(hold * 1000);
  }
  await page.screenshot({ path: path.join(output, 'screens', id + '.png') });
  timeline.push({ ...script, start: begin, end: elapsed(), audio_start: begin + .6, audio_duration: voices[id].duration });
  console.log(JSON.stringify({ scene: id, status: 'passed', seconds: +(elapsed() - begin).toFixed(1) }));
}
let videoPath;
try {
  await scene('startup', async () => {
    if (narration.language.startsWith('en')) {
      await page.setContent(`<html lang="en"><meta charset="utf-8"><style>body{margin:0;background:#f3f0e7;color:#183153;font-family:'Segoe UI',sans-serif;border-top:7px solid #183153}main{max-width:1260px;margin:85px auto}small{color:#9b2235;letter-spacing:4px}h1{font:64px Georgia,serif;margin:25px 0}h2{font:30px Georgia,serif;font-weight:400}section{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin:55px 0}article{background:#fffefb;border:1px solid #d9d0be;padding:28px;font-size:21px;border-top:3px solid #af8138}p{line-height:1.7;color:#596760}footer{color:#8e6b31;font-size:20px;letter-spacing:1px}</style><main><small>PROJECT DEMONSTRATION</small><h1>Calculus Atelier</h1><h2>An adaptive mathematics learning workspace</h2><section><article><strong>Focused practice</strong><p>Configurable exercises<br>Mathematical validation</p></article><article><strong>Traceable feedback</strong><p>Course-linked evidence<br>Searchable knowledge</p></article><article><strong>Learning insights</strong><p>Topic-level progress<br>Actionable next steps</p></article></section><footer>Practice. Understand. Reflect. Progress.</footer></main></html>`);
    } else {
    await page.setContent(`<html lang="zh-CN"><meta charset="utf-8"><style>body{margin:0;background:#f3f0e7;color:#183153;font-family:'Microsoft YaHei',sans-serif;border-top:7px solid #183153}main{max-width:1260px;margin:80px auto}small{color:#9b2235;letter-spacing:3px}h1{font-size:52px;margin:20px 0}h2{font-size:29px;font-weight:400}section{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:35px 0}article{background:#fffefb;border:1px solid #d9d0be;padding:26px;font-size:22px}p{line-height:1.8}.tag{color:#497366}footer{color:#6c706b;font-size:17px}</style><main><small>CALCULUS ATELIER · 演示说明卡（非应用页面）</small><h1>从本地启动，到可追溯的学习闭环。</h1><h2>Windows 本机验收 · 实际接口 · 合成学生记录</h2><section><article><strong>启动与健康检查</strong><p>start.ps1 · 已启动并预热<br>前端 ${base}<br>后端 ${apiBase} · HTTP 200</p></article><article><strong>真实运行范围</strong><p>本地检索：${caps.rag.device} · ${caps.rag.chunks} 个知识单元<br><span class="tag">付费接口：关闭</span><br>AI 回复与多角色推理：离线模板</p></article></section><footer>自动操作实际网页；不拦截或伪造接口响应。临时数据库与真实账户隔离。配音为本地合成语音。</footer></main></html>`);
    }
    checks.startup = { health_http_200: true, health_status: health.status, web: base, api: apiBase, warmed_before_recording: true, ai_mode: caps.ai_mode, external_calls_enabled: caps.external_calls_enabled, rag_device: caps.rag.device };
  });
  await scene('login', async () => {
    await page.goto(base); await expect(page.getByText('Offline AI simulation', { exact: true })).toBeVisible();
    await page.getByLabel('User ID', { exact: true }).fill(config.user_id);
    await page.getByLabel('Password', { exact: true }).fill(config.password);
    await click(page.getByRole('button', { name: 'Sign in', exact: true }));
    await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
    token = await page.evaluate(() => sessionStorage.getItem('t2p_access_token'));
    beforeCount = count(await apiProgress());
    checks.login = { actual_password_login: true, account: config.user_id, independent_attempts_before: beforeCount };
  });
  await scene('generate', async () => {
    await page.getByLabel('Knowledge dimension').selectOption('Derivatives and Differentiation');
    await generate('mcq');
    await expect(page.getByRole('button', { name: /^Option A:/ })).toBeVisible();
    checks.generation = { actual_api: true, learner_answer_key_hidden: true, problem_id: question.id };
  });
  await scene('wrong', async () => {
    const entry = Object.entries(question.options).find(([, value]) => value.replaceAll('$', '').trim().startsWith('-'));
    if (!entry) throw new Error('Expected a visibly negative distractor for this positive chain-rule derivative.');
    wrongOption = entry[0];
    const wait = page.waitForResponse(r => r.url() === apiBase + '/audit' && r.request().method() === 'POST');
    const option = page.getByRole('button', { name: new RegExp('^Option ' + wrongOption + ':') });
    await click(option);
    const response = await wait; expect(response.ok()).toBeTruthy(); const result = await response.json();
    expect(result.is_correct).toBe(false); expect(result.logic_alignment_score).toBe(0); expect(result.progress_recorded).toBe(true);
    await expect(option).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByText('Learning record saved by the server.')).toBeVisible();
    await page.getByRole('region', { name: 'Mentor review', exact: true }).scrollIntoViewIfNeeded();
    checks.wrong_answer = { score: 0, selection_persists: true, progress_recorded: true };
  });
  await scene('source', async () => {
    const wait = page.waitForResponse(r => r.url().includes('/knowledge/chunks/'));
    await click(page.getByRole('button', { name: /\[C1\]/ }));
    const response = await wait; expect(response.ok()).toBeTruthy(); const result = await response.json();
    const dialog = page.getByRole('dialog', { name: 'Course source' });
    await expect(dialog).toBeVisible(); await expect(dialog.getByText('Chain rule', { exact: false }).first()).toBeVisible();
    expect(result.data.id).toBe('derivative-chain');
    checks.citation = { source_id: result.data.id, version: result.data.source_version, actual_source_request: true };
  });
  await scene('correct', async () => {
    await click(page.getByRole('button', { name: 'Close course source' }));
    await generate('calculation');
    const solved = JSON.parse(execFileSync(path.join(root, '.venv/Scripts/python.exe'),
      [path.join(root, 'scripts/prepare_demo.py'), '--folder', folder, '--solve', question.id], { cwd: root, encoding: 'utf8', windowsHide: true }));
    const field = page.getByRole('textbox', { name: /Final expression/ }); await field.fill(solved.expression);
    const wait = page.waitForResponse(r => r.url() === apiBase + '/audit' && r.request().method() === 'POST');
    await click(page.getByRole('button', { name: 'Submit typed answer' }));
    const response = await wait; expect(response.ok()).toBeTruthy(); const result = await response.json();
    expect(result.is_correct).toBe(true); expect(result.logic_alignment_score).toBe(100); expect(result.progress_recorded).toBe(true);
    await expect(page.getByText('Your answer agrees with the stored reference.', { exact: false })).toBeVisible();
    checks.correct_answer = { score: 100, solver: solved.method, expanded_equivalent_expression_accepted: true, progress_recorded: true };
  });
  await scene('progress', async () => {
    await click(page.getByRole('link', { name: 'Progress Report' }));
    await expect(page.getByRole('heading', { name: 'Academic Progress Report' })).toBeVisible();
    await expect(page.getByRole('img', { name: /Aggregated calculus domain mastery/ })).toBeVisible();
    const progress = await apiProgress(); afterCount = count(progress); expect(afterCount).toBe(beforeCount + 2);
    await page.evaluate(() => scrollTo({ top: 180, behavior: 'smooth' }));
    checks.progress = { independent_attempts_before: beforeCount, independent_attempts_after: afterCount, actual_new_records: 2,
      topics: Object.keys(progress.topics_status).length, total_minutes: progress.total_minutes,
      synthetic_history: true, recommendation_present: Boolean(progress.recommendation) };
  });
  await scene('recommendation', async () => {
    await page.getByRole('heading', { name: 'Learning brief', exact: true }).scrollIntoViewIfNeeded();
    await expect(page.getByText('Observed concept attempts · not a mastery estimate')).toBeVisible();
    checks.recommendation = { topic_and_concept_evidence_visible: true };
  });
  await scene('library', async () => {
    await page.goto(base + '/knowledge');
    await expect(page.getByRole('heading', { name: 'Course collection' })).toBeVisible();
    await page.locator('.library-search select').selectOption('Applications of Derivatives');
    await page.getByLabel('Search course notes', { exact: true }).fill('marginal cost');
    const wait = page.waitForResponse(r => r.url().includes('/knowledge/search?'));
    await click(page.getByRole('button', { name: 'Search', exact: true }));
    const response = await wait; expect(response.ok()).toBeTruthy(); const result = await response.json();
    expect(result.data.evidence.some(c => c.id === 'derivative-marginal-cost')).toBe(true);
    await expect(page.getByRole('heading', { name: /Marginal cost and rates/ })).toBeVisible();
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
    checks.library = { actual_hybrid_search: result.data.method === 'hybrid', marginal_cost_source_found: true, knowledge_units: caps.rag.chunks };
  });
  await scene('agents', async () => {
    await page.goto(base); await click(page.getByRole('navigation').getByRole('button', { name: 'Agent Laboratory', exact: true }));
    await expect(page.getByRole('heading', { name: 'Agent Laboratory', exact: true })).toBeVisible();
    const topics = page.locator('.lab-topic-list');
    for (const button of await topics.getByRole('button', { pressed: true }).all()) {
      if (!(await button.textContent()).includes('Derivatives and Differentiation')) await click(button);
    }
    const derivative = topics.getByRole('button', { name: /Derivatives and Differentiation/ });
    if (await derivative.getAttribute('aria-pressed') !== 'true') await click(derivative);
    const slider = page.locator('.lab-configuration input[type=range]').first(); await slider.focus(); await slider.press('Home');
    await expect(slider).toHaveValue('1');
    await click(page.getByRole('button', { name: 'Start synthesis', exact: true }));
    await expect(page.getByText('Synthesis complete', { exact: true })).toBeVisible({ timeout: 90_000 });
    const metrics = page.locator('.lab-result-card'); await metrics.scrollIntoViewIfNeeded();
    await expect(metrics.locator('.lab-metric-grid > div').filter({ hasText: 'LLM calls' }).locator('strong')).toHaveText('0');
    await expect(metrics.locator('.lab-metric-grid > div').filter({ hasText: 'Problems' }).locator('strong')).toHaveText('1');
    checks.agents = { scripted_role_simulation: true, llm_calls: 0, saved_problems: 1, actual_synthesis_completed: true };
  });
  await scene('ending', async () => {
    await click(page.getByRole('navigation').getByRole('button', { name: 'Problem Studio', exact: true }));
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'smooth' }));
    expect(count(await apiProgress())).toBe(afterCount);
    checks.final_record_stable = true;
  });
  expect(criticalErrors).toEqual([]); expect(failedRequests).toEqual([]);
} catch (error) {
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
  await fs.writeFile(path.join(output, 'failure.txt'), String(error.stack));
  throw error;
} finally {
  const video = page.video(); await context.close(); if (video) videoPath = await video.path(); await browser.close();
  const report = { mode: rehearsal ? 'rehearsal' : 'recorded_acceptance', completed: timeline.length === narration.scenes.length,
    real_api_responses: true, paid_api_calls: 0, narration_file: narrationFile, language: narration.language,
    synthetic_isolated_account: true, warmed_before_recording: true, checks, criticalErrors, failedRequests,
    duration: elapsed(), timeline, videoPath,
    known_limitations: ['AI replies and role reasoning are offline fixtures, not live DeepSeek.',
      'History is synthetic practice and is not an actual course grade.',
      'Study minutes are not inferred from the accelerated seed or this recording; zero minutes is not fabricated into hours.',
      'Scripted synthesis average quality may display 0.0 as an unmeasured placeholder, not a teaching-quality result.',
      'Source existence and concept matching are not independent proof of explanation correctness.'] };
  await fs.writeFile(path.join(output, rehearsal ? 'rehearsal.json' : 'acceptance.json'), JSON.stringify(report, null, 2));
  await http.dispose();
}
console.log(JSON.stringify({ status: 'passed', rehearsal, output, videoPath, elapsed_seconds: +elapsed().toFixed(1) }));
