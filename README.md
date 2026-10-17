# Calculus Atelier

Calculus Atelier is an adaptive calculus learning system that combines structured LLM
generation, handwritten-solution auditing, deterministic mathematics checks,
and multi-agent dataset curation.

中文简介：一个面向微积分学习的自适应智能教学系统，将题目生成、选择题确定性判分、
手写过程审查、学习画像与多智能体题库生产整合为完整学习流程。
本项目源自硕士毕业设计；仓库保留原研究名称，当前应用品牌为 **Calculus Atelier**。

[Quick start](#quick-start) · [Validation and grading](#deterministic-validation) ·
[Testing](#verification) · [Deployment](#production-profile) ·
[Interview guide](docs/INTERVIEW_GUIDE.md)

The project is designed around one principle: language models may create and
review educational content, but they must not be the only authority on
machine-checkable mathematics.

## What the system does

- Generates drill and integrated-exam calculus problems.
- Supports calculation, multiple-choice, and fill-in formats.
- Includes 252 reference problems across 13 calculus topics: 122 calculation,
  65 multiple-choice, and 65 fill-in problems.
- Grades MCQ selections through exact backend comparison and uses AI for explanations.
- Transcribes handwritten work and provides tutor feedback when a separate vision
  provider is configured.
- Tracks topic mastery and recommends the next learning task.
- Presents an Academic Progress Report with six aggregated domains, detailed topic
  mastery bars, levels, exercise counts, and learning suggestions.
- Authenticates learners with strong password hashing and revocable sessions.
- Runs an offline multi-agent pipeline for higher-quality dataset synthesis.
- Streams agent events to the frontend using Server-Sent Events.
- Validates generated problem structure and symbolic claims before publishing.

## Architecture

```text
Next.js academic learning workspace
             |
             v
FastAPI request validation and error boundary
             |
      +------+-------------------+
      |                          |
Online generation          Offline synthesis
      |                          |
Topic/type prompts        Synthesizer / Scaffolder
      |                          |
LLM structured output      Reviewer / Curator
      +------------+-------------+
                   |
        Pydantic canonical schema
                   |
        SymPy deterministic gate
                   |
       SQLAlchemy repository layer
                   |
       SQLite / PostgreSQL + JSON artifacts

Submission review:
  MCQ -> exact stored answer-key comparison -> AI explanation
  Photo/canvas -> dedicated vision OCR -> text mentor review
  Both -> stored submission -> learning-result recording -> progress report
```

Online generation uses a lighter generation/review loop for interactive practice.
Dataset synthesis permits more review, revision, and provider calls. The four
agent roles communicate through a message bus:

| Agent | Responsibility |
|---|---|
| Synthesizer | Generate complete questions and revise rejected work |
| Scaffolder | Design progressive learning hints |
| Reviewer | Review mathematical/pedagogical quality and reject invalid work |
| Curator | Monitor coverage and request additional content |

The coordinator starts agents and monitors completion, timeout, and failure.

### Quality states

Generated content is never auto-approved when a reviewer fails. A problem may
be:

- `passed`: schema and symbolic claim both passed.
- `partial`: schema and invariants passed, but no symbolic claim was supplied.
- `validation_failed`: deterministic checks found an error.
- `review_failed`: the quality reviewer did not produce a reliable verdict.
- `approved`: deterministic validation and pedagogical review passed.

Validation and publishing use separate status fields. A `partial` check does not
prove the complete solution, and an LLM approval is not human certification.

## Technology

- Backend: Python, FastAPI, Pydantic, SymPy, SQLAlchemy
- Persistence: SQLite locally or PostgreSQL for multi-user deployment
- Observability: OpenTelemetry, Jaeger, and Prometheus
- AI integration: DeepSeek text reasoning plus a dedicated OpenAI-compatible vision OCR API
- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS
- Mathematics: KaTeX and SymPy
- Visualization: Recharts and Matplotlib
- Testing: pytest, Playwright with Chrome, ESLint, and Next.js production build

## Quick start

Prerequisites: Python 3.10+, Node.js 20.9+ with npm, Git, and valid text-model API
credentials. Commands below target Windows PowerShell; `npm.cmd` avoids execution
policy problems with the `npm.ps1` wrapper.

```powershell
git clone https://github.com/951135150/Generative-AI-Data-Synthesis-System-for-Mathematics-Learning.git
cd Generative-AI-Data-Synthesis-System-for-Mathematics-Learning
```

### 1. Configure the backend

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Fresh checkout only; keep an existing .env when updating.
Copy-Item .env.example .env
```

For a fresh clone, copy `.env.example` to `.env` and replace its placeholders.
Keep your existing private `.env` when updating an existing checkout. The text
model is required; the vision configuration is optional:

```dotenv
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_MODEL=your-provider-supported-text-model

VISION_PROVIDER=openai-compatible
VISION_API_KEY=your-vision-provider-key
VISION_BASE_URL=https://api.openai.com/v1
VISION_MODEL=your-vision-capable-model
```

Use a model identifier your provider/account supports; older reports and code
defaults do not guarantee current API availability. `VISION_MODEL` must accept
OpenAI-compatible `image_url` message content. The
backend reports the effective, non-secret configuration at `/capabilities`.

Keep `ENABLE_SEMANTIC_DEDUP=false` for a first run. This uses text fingerprints
and avoids downloading an embedding model.

After editing `.env`, start the backend:

```powershell
.\.venv\Scripts\python.exe api_server.py
```

The API runs at `http://127.0.0.1:8001`. Interactive API documentation is
available at `/docs`.

### 2. Start the frontend

In a second terminal, from the project root:

```powershell
cd t2p-web
npm.cmd ci
npm.cmd run dev
```

Open `http://localhost:3000`.

| Service | Default local address |
|---|---|
| Frontend | http://localhost:3000 |
| API health | http://127.0.0.1:8001/ |
| API documentation | http://127.0.0.1:8001/docs |
| Configured AI capabilities | http://127.0.0.1:8001/capabilities |
| Playwright frontend | http://127.0.0.1:3100 (managed by the test runner) |

Register through the frontend to save progress. The repository contains no
preconfigured learner password or personal account database.

### Alternate ports

When default ports are occupied, run the backend from the project root:

```powershell
$env:FRONTEND_ORIGINS = 'http://localhost:3001,http://127.0.0.1:3001'
.\.venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8002
```

In a separate terminal, from `t2p-web`:

```powershell
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8002'
npm.cmd run dev -- --hostname 127.0.0.1 --port 3001
```

Open http://127.0.0.1:3001. Local origins on ports `3000` and `3001` are allowed
by default. `FRONTEND_ORIGINS` replaces that list with comma-separated origins.
For other ports, update both the API URL and allowed origins and restart the
services. Browser origins distinguish `localhost` from `127.0.0.1`.

### Photo review architecture

Photo submissions use a strict two-model pipeline:

```text
JPEG / PNG / WebP (maximum 5 MB)
    -> dedicated vision OCR provider
    -> faithful LaTeX/text transcript
    -> configured DeepSeek text-only grading
    -> structured score and tutor feedback
```

Images are never sent to DeepSeek. If vision OCR is missing or fails, the API
returns `VISION_OCR_NOT_CONFIGURED` or `VISION_OCR_FAILED`; it does not silently
invent a transcript or fall back to an incompatible text model. The frontend
shows the current capability state and disables photo submission until the
vision provider is ready.

Canvas handwriting uses this same pipeline. Configuration readiness does not
guarantee a successful provider request: network, quota, and unsupported model
errors can still occur. OCR must preserve the student's work rather than solve it.

### 3. Migrate existing project data

The migration is idempotent: it can be run repeatedly and does not delete or
rewrite the original JSON files.

```powershell
.\.venv\Scripts\python.exe migrate_json_to_sqlite.py
```

SQLite is the runtime source of truth for users, topic mastery, learning
events, generated problems, submissions, and generation runs. JSON remains an
inspectable generation artifact. Set `MIRROR_JSON_PROGRESS=true` only when an
older integration still needs progress-file mirrors.

### 4. Restore the interview demo record

On a fresh clone, first register `student_01` in the frontend using a password of
your choice. Then prepare its synthetic B-grade interview record:

```powershell
.\.venv\Scripts\python.exe -m scripts.seed_student_demo
```

The command creates an online SQLite backup in `data/backups/`, then replaces
only this account's mastery and learning-event history. It is safe to run more
than once, does not change the account password, and produces an 84% average
mastery profile with 62 completed exercises, a clear differential-calculus
strength, and one concrete next priority.

The profile includes 15 hours of recorded study and multiple integrals as a
learning priority. These are demonstration records, not measured student outcomes.
The displayed B is derived from mastery, not an externally awarded course grade.
For an existing local account, reset its password interactively if needed:

```powershell
.\.venv\Scripts\python.exe manage_user.py set-password student_01
```

A short walkthrough: sign in, generate one drill-mode MCQ, select an option,
explain the grading/feedback split, open Progress, and show Agent Laboratory.
Use a small synthesis task because multi-agent review and retries add latency.

### Learning policy

Recorded results update mastery using
`new_mastery = 0.4 × previous_mastery + 0.6 × (score / 100)`.
Correct results scoring at least 80 can advance a topic up to level 3. The
adaptive selector scans the curriculum for the first topic below 85% mastery
and chooses difficulty and mode from its level. This is a rule-based policy,
not a trained knowledge-tracing model. The radar chart aggregates recorded
topics into six domains using unweighted means; detailed topic values remain
visible in the report.

## Deterministic validation

Generated problems use a canonical Pydantic schema. When a mathematical claim
can be represented symbolically, the generator also emits:

```json
{
  "symbolic_validation": {
    "operation": "differentiate",
    "source_expression": "x^3 + 2*x",
    "claimed_result": "3*x^2 + 2",
    "variable": "x"
  }
}
```

SymPy checks the claim independently of the LLM. Supported operations are
`differentiate`, `integrate`, `simplify`, and `limit`. Problems with failed
claims cannot be saved by the multi-agent publishing tool.

Online generation also runs a separate semantic quality review. For newly
generated MCQs, this review must explicitly confirm that the stored answer key
points to the mathematically correct option. Its outcome is recorded in
`answer_validation`. This check is distinct from verifying that a key merely
exists, and it does not retroactively certify legacy questions.

### Deterministic MCQ grading

The frontend sends an option key, while the backend reads the complete question
and reference answer from storage:

```json
{
  "problem_id": "your-generated-problem-id",
  "selected_option": "D",
  "is_exam_mode": false
}
```

The backend compares the keys and awards **100 for a match or 0 for a mismatch**.
The mentor model receives the question, all option contents, selected content,
reference content, solution, and deterministic verdict. It generates an
explanation without overriding the score. Contradictory verdicts, malformed
JSON, and model exceptions fall back to consistent MCQ feedback. Invalid stored
answer keys produce `INVALID_REFERENCE_ANSWER` rather than marking the learner
wrong. Exact comparison still depends on a correct stored reference answer.

## API overview

| Method | Route | Purpose |
|---|---|---|
| GET | `/` | Report backend health, dataset size, persistence, and observability |
| GET | `/capabilities` | Report text grading and vision OCR readiness without exposing secrets |
| GET | `/topics` | List supported calculus topics |
| POST | `/auth/register` | Create a password-protected learner account |
| POST | `/auth/login` | Create a revocable bearer session |
| GET | `/auth/me` | Restore and verify the current session |
| POST | `/auth/logout` | Revoke the current session |
| POST | `/generate` | Generate validated practice content |
| POST | `/audit` | Audit a typed or handwritten submission |
| POST | `/user/record` | Record a learning result |
| GET | `/user/progress/{id}` | Retrieve mastery data |
| POST | `/synthesize` | Run multi-agent dataset synthesis |
| GET | `/synthesize/stream` | Stream synthesis events |

All API failures use a consistent response containing an error code, safe
message, and request ID.

The old identity-only `/user/login` route is retired; use password authentication.

## Verification

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run the frontend production check:

```powershell
cd t2p-web
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e
```

Latest code-sync verification: **45 backend tests and 4 Playwright tests passed**,
alongside lint and the production build. Coverage includes authentication,
ownership, transactions, migration, validation, MCQ conflicts, OCR failures,
and benchmark manifests. Playwright requires installed Google Chrome and
intercepts API calls with deterministic fixtures while exercising the real UI.
These tests do not verify live provider availability or educational effectiveness.

Generate the reproducible single-agent versus multi-agent comparison:

```powershell
.\.venv\Scripts\python.exe evaluate_system.py
```

This produces `reports/evaluation_report.json`,
`reports/evaluation_report.md`, and a fixed 100-case
`reports/benchmark_tasks.json` manifest. The offline analysis performs no paid
model calls; the task manifest can also be used for a controlled live A/B run.

The analyzer reads local `output/` and `output/multi_agent/` artifacts. These are
excluded from Git, so a fresh clone does not contain the historical generated
samples. Checked-in reports are snapshots; rerunning without those local inputs
will not reproduce their historical sample counts.

Prepare the fully paired, topic-stratified A/B experiment:

```powershell
.\.venv\Scripts\python.exe ab_benchmark.py prepare
```

The default manifest contains 300 matched cases across 10 topics, covering five
difficulties, three question types, and two modes. Both pipelines run each case,
producing 600 generation tasks; review/retry loops can require additional model
calls. Execution order is counterbalanced. Live execution requires the explicit
`--confirm-live-calls` flag because it can consume substantial model quota.

```powershell
.\.venv\Scripts\python.exe ab_benchmark.py run --limit 5 --confirm-live-calls
.\.venv\Scripts\python.exe ab_benchmark.py evaluate
```

Evaluation supports paired differences and 95% bootstrap confidence intervals.
The complete live experiment is not claimed finished. Historical sample sizes
and topic coverage are unequal, so schema acceptance rates alone cannot prove
that one pipeline is mathematically superior.

## Production profile

`compose.yaml` provides PostgreSQL, an OpenTelemetry Collector, Jaeger, and
Prometheus. These are infrastructure services; start the API and frontend
separately. Keep the text-model settings in your private `.env` and add the
database/telemetry values from [.env.postgres.example](.env.postgres.example):

```dotenv
POSTGRES_PASSWORD=your-private-database-password
DATABASE_URL=postgresql+psycopg://t2p:your-private-database-password@127.0.0.1:5432/t2p
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
```

Use the same password in both settings and URL-encode reserved characters in
the connection URL. Then:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe migrate_legacy_data.py
.\.venv\Scripts\python.exe api_server.py
```

Jaeger is available at `http://127.0.0.1:16686` and Prometheus at
`http://127.0.0.1:9090`. See `docs/PRODUCTION_GUIDE.md` for authentication,
database, observability, benchmark, and E2E details.

Responses include `X-Request-ID` and, with tracing enabled, `X-Trace-ID`.
For a local production-style frontend demo, run `npm.cmd run build` and then
`npm.cmd run start` in `t2p-web`. Set `NEXT_PUBLIC_API_URL` before building if
using another backend. Public hosting needs a reachable API, HTTPS, and matching
allowed origins; a localhost URL is only accessible on the machine running it.

## Repository map

```text
api_server.py          FastAPI routes and submission orchestration
src/generator.py      Online generation and revision
src/evaluator.py      Mathematical and pedagogical quality review
src/grading.py        Exact MCQ option assessment
src/ocr.py            Dedicated vision transcription
src/multi_agent/      Agents, coordinator, message bus, and tools
src/schemas/          Canonical question and API request models
src/validation/       Structural and symbolic validation
src/database/         SQLAlchemy models, repositories, and migration
src/evaluation/       Offline and paired A/B analysis
t2p-web/              Next.js application and browser tests
scripts/              Synthetic demo-profile setup
tests/                Backend regression tests
docs/                 Interview and production guides
observability/        Collector and Prometheus configuration
reports/              Report snapshots and experiment manifests
```

Private `.env` files, account databases, personal progress, local backups,
generated outputs, and runtime caches are excluded from version control.

## Interview discussion points

- Why online generation and offline multi-agent synthesis have different
  latency and quality requirements.
- Why symbolic verification and LLM pedagogical review are separate stages.
- How canonical schemas prevent frontend/backend contract drift.
- Why failed reviewers produce explicit failure states instead of fallback
  approval.
- How atomic writes prevent partially written progress and problem records.
- Why repositories and short SQL transactions make concurrent API writes safer
  than directly mutating JSON.
- How an idempotent migration enables a staged persistence upgrade without
  discarding inspectable legacy artifacts.
- How the fixed-seed benchmark prevents cherry-picked single-agent versus
  multi-agent comparisons.
- Why opaque session tokens are stored only as hashes and can be revoked.
- How OpenTelemetry correlates FastAPI, outbound HTTPX, and SQLAlchemy spans.
- How request IDs and stable error codes improve debugging without exposing
  internal exceptions.

## Current limitations

- Symbolic validation covers explicit machine-readable claims, not every proof
  or natural-language reasoning step.
- Existing legacy problems do not all contain machine-readable symbolic claims;
  the evaluation report makes that coverage gap explicit.
- The current multi-agent sample is smaller and less topic-diverse than the
  single-agent corpus, so quality comparisons should be interpreted alongside
  sample size and topic coverage.
- LLM quality and latency depend on the configured provider.
- Handwritten feedback depends on a separately configured vision model and can
  be affected by OCR mistakes. Independent LLM review can share generator errors.
- Fill-in content is supported, but there is no dedicated deterministic fill-in
  grader comparable to the MCQ path.
- Difficulty, mastery thresholds, and learning outcomes have not been calibrated
  through a large longitudinal student study; the interview profile is synthetic.
- Password sessions currently use browser session storage; a same-origin
  production deployment can further harden this with Secure HttpOnly cookies.
- The separate authenticated result-recording endpoint currently accepts scores
  from the client. Stronger production integrity would link updates to stored
  server-graded submissions and enforce idempotency.
