# Calculus Atelier

### RAG & Multi-Agent Mathematics Learning System

Calculus Atelier is a local retrieval-augmented adaptive calculus learning system.
It combines versioned course references, hybrid retrieval, structured generation,
deterministic mathematics checks, and multi-agent dataset curation.

中文简介：基于 RAG 与多智能体协作的自适应数学学习系统，将课程知识检索、可追溯引用、
题目生成、确定性判分、学习画像与多智能体题库生产整合为学习流程。
本项目源自硕士毕业设计；仓库保留原研究名称，当前应用品牌为 **Calculus Atelier**。

[Windows setup](#windows-local-rag-edition--zero-paid-api-calls-by-default) ·
[RAG and sources](#retrieval-and-knowledge-management) ·
[Validation](#deterministic-validation) · [Testing](#verification) ·
[Demo](#project-demonstration) · [Troubleshooting](#troubleshooting) ·
[Optional infrastructure](#optional-infrastructure-profile) ·
[Interview guide](docs/INTERVIEW_GUIDE.md)

The project is designed around one principle: language models may create and
review educational content, but they must not be the only authority on
machine-checkable mathematics.

## Windows local RAG edition — zero paid API calls by default

The default `AI_MODE=simulation` uses explicit, parameterized teaching fixtures.
Retrieval, CUDA/CPU selection, mathematics checks, accounts, submissions, and
learning records run locally. The agent laboratory uses scripted role replies
in this mode, not autonomous model reasoning. All thirteen topics have small
MCQ/calculation/fill-in fixtures. These do not cover the full syllabus or measure
real model quality. Typed simulation submissions check final expressions,
not free-form proofs or handwriting.

NVIDIA CUDA is preferred automatically; CPU is used if GPU initialization or
encoding fails. No Docker, cloud account, PostgreSQL server, or paid API is
required for this workflow. Existing Docker/cloud files are retained as legacy
optional infrastructure outside the Windows local implementation.

With Python 3.10–3.12 and Node.js 20.9+ installed:

```powershell
git clone https://github.com/951135150/Generative-AI-Data-Synthesis-System-for-Mathematics-Learning.git
cd Generative-AI-Data-Synthesis-System-for-Mathematics-Learning
# First run: install dependencies and download the free embedding model.
.\setup.ps1 -DownloadModel

# Subsequent runs: launch the backend and frontend in offline simulation mode.
.\start.ps1
```

The first model download needs internet; subsequent retrieval is local. Model
and package caches use `.runtime` on the project drive. Setup reuses an existing
working CUDA PyTorch installation. The launcher preserves `.env`, backs up SQLite,
checks ports, and owns only the server processes it starts. Press Ctrl+C to stop.

Setup requires the Windows Python launcher (`py`) if it creates `.venv`; ensure
`py -3` selects Python 3.10–3.12. It installs `constraints-windows.txt`, runs
`npm ci`, creates `.env` only if absent, and preserves a working CUDA installation.
Without `-DownloadModel`, model provisioning is skipped. If PowerShell blocks
scripts, use a per-command override rather than changing machine-wide policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -DownloadModel
```

The verified GPU is a GTX 1650 4 GB with PyTorch 2.7.1+cu118. There is no local
generative LLM download. The prepared E5 cache was approximately 466 MiB;
Python/CUDA packages, npm dependencies, build caches and backups add separate
overhead. This is not a total installation-size estimate. A clean setup on a
second Windows machine remains to be verified.

Default addresses are frontend `http://127.0.0.1:3000` and API
`http://127.0.0.1:8001`. For occupied ports, use
`.\start.ps1 -ApiPort 8002 -WebPort 3001`; frontend URL and allowed origins are
synchronized. Unrelated applications are never stopped to free a port.

For the existing development workspace, the embedding model is already prepared.
Do not rerun dependency installation unless needed.

```powershell
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe scripts/simulate_students.py
.\.venv\Scripts\python.exe scripts/evaluate_rag.py
```

Student simulation uses a separate database under `.runtime/student-tests`, never
`student_01`. Read [local RAG implementation and limitations](docs/LOCAL_RAG.md)
for source import, manual assistant roundtrips and verification details.

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

### Workspace and curriculum

The academic interface uses cream backgrounds, navy accents, serif headings and
restrained gold/burgundy details. **Problem Studio** brings together configuration,
mathematical rendering, persistent MCQ selection and mentor review. **Progress
Report** combines six-domain radar and detailed topic bars. **Course Library**
supports source browsing/search, and **Agent Laboratory** exposes synthesis events.

The 13 topics are Limits and Continuity; Derivatives and Differentiation;
Integration and FTOC; Multivariable Calculus; Applications of Derivatives;
Indefinite Integrals; Applications of Integration; Multiple Integrals; Vector
Calculus; Sequences and Series; Differential Equations; Techniques of Integration;
and Parametric and Polar Curves. Three fixture formats per topic do not constitute
complete syllabus coverage or empirically calibrated difficulty.

## Retrieval and knowledge management

Bundled course notes are version **1.1**, with **18 knowledge units** across
13 topics. They are original project references, not certified textbook excerpts.
Generated questions do not automatically become trusted course knowledge.

Retrieval combines BM25 lexical ranking, normalized
`intfloat/multilingual-e5-small` embeddings and reciprocal rank fusion (RRF).
Model revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Vectors are cached
locally; CUDA loading/encoding failures fall back to CPU. Dense-model failure
is reflected as keyword-only or unavailable retrieval status, not silently
reported as successful hybrid retrieval.

Tutor retrieval filters by problem concept tags where present. Insufficient
matching evidence does not trigger unrelated same-topic citations. Evidence
snapshots retain source/version/hash information, and source dialogs detect
changed or withdrawn passages. Valid IDs and concept overlap do not prove that
every explanation claim is independently supported.

Learners can browse and search published material in **Library**. Administrators
can preview imports, save drafts, publish reviewed sources and withdraw material.
Registration grants no administrative permissions. On your own machine:

```powershell
.\.venv\Scripts\python.exe manage_user.py set-role YOUR_ACCOUNT_ID admin
```

Role changes back up local SQLite. Sign out and in again; use `student` to revoke
the role. Publication checks review confirmation, the actual local tokenizer's
512-token limit and source hash consistency. Stale writes return 409 and earlier
manifests are archived. This targets the local single-process server.

Imports support Markdown/text, structured JSON and text-readable PDF, limited to
5 MB, 50 PDF pages and 100 semantic units. Scanned PDFs need separate OCR; the
importer does not transcribe images. Prepare the embedding model before publishing.
Oversized units must be split and reviewed instead of silently truncating formulas.

```powershell
.\.venv\Scripts\python.exe scripts/knowledge.py list
.\.venv\Scripts\python.exe scripts/knowledge.py import `
  --file D:/course/notes.md --source-id my-course --title "Course notes" `
  --version 1 --topic "Derivatives and Differentiation" `
  --provenance "Original notes by the course author" --license "Private course use"
```

Imports default to draft and are excluded from retrieval. Add `--publish` only
after reviewing rights, extracted formulas and mathematics. CC0 metadata applies
only to the new bundled notes, not the whole repository. Full instructions:
[local RAG and source administration](docs/LOCAL_RAG.md).

## Architecture

### Runtime modes

| Component | Default simulation | Optional live mode |
|---|---|---|
| Retrieval | Actual local BM25/E5/RRF | Same retrieval pipeline |
| Generation | Parameterized fixtures | Configured text-model provider |
| Mentor | Templates and MCQ/final-expression checks | Text-model explanation and review |
| Agent Laboratory | Scripted replies; real transport, validation and storage | Model-driven replies |
| Photo/canvas | Disabled | Separate vision provider required |
| Accounts and progress | Actual local persistence | Same persistence layer |

An API key alone never enables external model access: both `AI_MODE=live` and
`ALLOW_PAID_API=true` are required. Simulation is workflow verification, not a
measure of autonomous model reasoning or educational effectiveness.

### Component flow

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
      Purpose-specific course retrieval
      BM25 + E5 + RRF / evidence snapshots
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
  Typed fixture -> SymPy final-expression equivalence -> feedback
  Photo/canvas -> dedicated vision OCR -> text mentor review
  All -> stored submission + retry receipt -> learning record -> report
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

## Manual setup and optional live configuration

Prerequisites: Python 3.10–3.12, Node.js 20.9+ with npm, and Git. A text-model API
key is required only for explicit live mode. Commands below target Windows PowerShell; `npm.cmd` avoids execution
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
Keep your existing private `.env` when updating an existing checkout. External
models are optional. Live text and OCR calls require both `AI_MODE=live` and
`ALLOW_PAID_API=true`; an API key alone never enables paid access. Example:

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

Keep `ENABLE_SEMANTIC_DEDUP=false` for a first run. This uses fingerprints for
generation deduplication and avoids an additional deduplication model; it does
not disable the separate E5 course-retrieval model.

For live use, set both `AI_MODE=live` and `ALLOW_PAID_API=true`, then launch the
API manually. `start.ps1` intentionally forces safe simulation even if `.env`
contains live settings. Prepare the free retrieval model separately with
`scripts/prepare_rag.py --download` and keep `RAG_ALLOW_DOWNLOAD=false` at runtime.

Other useful variables include `RAG_CACHE_DIR` and `KNOWLEDGE_PATH` for local
paths, `DATABASE_URL` and `OUTPUT_DIR` for persistence/artifacts,
`AUTH_SESSION_HOURS` (24), `PASSWORD_PBKDF2_ITERATIONS` (600000), and
`FRONTEND_ORIGINS` for allowed browser origins. `NEXT_PUBLIC_API_URL` configures
the frontend API address and must be set before build/start. Configuration
readiness and actual effective retrieval state are exposed by `/capabilities`.

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
Promotion requires at least three independent attempts, a correct latest answer
and mastery at least 0.8; levels are capped at 3. Recommendations prioritize topic
weakness, recent errors, repeated weak concept evidence and overdue practice,
checking reviewed prerequisites and providing a visible reason. This is a
rule-based policy, not a trained knowledge-tracing model. The radar chart uses
unweighted topic means across six domains; detailed topic values remain visible.

Review reminders follow a transparent 3/7/14-day rule after at least three
independent exercises and a latest correct score of at least 80. Longer correct
streaks extend the interval. Concept percentages describe observed first-attempt
accuracy, not inferred latent mastery or calibrated ability.

Submissions, evidence, progress and retry receipts are saved in one transaction.
Replaying an `attempt_id` with identical content returns the original response;
changing its content returns 409. Only the first attempt per stored question earns
learning credit. Later answers remain recorded without inflating exercise counts.

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

New scalar-expression MCQs additionally require machine-readable
`option_expressions`, an equivalence policy, excluded points and a symbolic claim.
The gate checks option display/expression agreement, reference correctness,
domain preservation and unique correct options. Indefinite-integral distractors
equivalent up to an additive constant must not be counted as distinct wrong
answers. Legacy questions without this metadata remain unverified/partial;
known ambiguous antiderivative questions require review before grading. Arbitrary
prose, tuple answers and rich interval-domain constraints remain outside this gate.

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

### Typed answers and feedback boundaries

Calculation and fill-in fixtures accept a final SymPy-style expression, such as
`6*x+2`. Simulation checks equivalence and allows an additive constant only when
the problem explicitly permits it. It does not understand arbitrary prose proofs
or handwritten derivations. A general live fill-in response is not universally
covered by the same deterministic guarantees.

Learner responses omit stored answer keys, solutions and internal symbolic claims.
Stored exam mode controls restrictions even if the client submits a different
flag. Feedback distinguishes reference mismatch from a misconception diagnosis:
one wrong option alone is not enough to establish a persistent misconception.

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
| POST | `/user/record` | Retired (410); progress is recorded atomically by `/audit` |
| GET | `/user/progress/{id}` | Retrieve mastery data |
| GET | `/knowledge/sources` | List published course sources and retrieval status |
| GET | `/knowledge/chunks/{id}` | Open a published reference, optionally checking its content hash |
| GET | `/knowledge/catalog` | Browse published course units |
| GET | `/knowledge/search` | Topic-filtered hybrid retrieval |
| GET | `/knowledge/manage/sources` | Administrator source list |
| GET | `/knowledge/manage/sources/{id}` | Administrator source details |
| POST | `/knowledge/manage/preview` | Read-only import preview |
| POST | `/knowledge/manage/save` | Save source content with conflict checks |
| POST | `/knowledge/manage/sources/{id}/status` | Publish or withdraw reviewed material |
| POST | `/synthesize` | Run multi-agent dataset synthesis |
| GET | `/synthesize/stream` | Stream synthesis events |

All API failures use a consistent response containing an error code, safe
message, and request ID.

The old identity-only `/user/login` route is retired; use password authentication.

## Verification

Run backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts/simulate_students.py
.\.venv\Scripts\python.exe scripts/evaluate_rag.py
.\.venv\Scripts\python.exe scripts/verify_course_workflow.py
```

Run the frontend production check:

```powershell
cd t2p-web
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e
```

Local RAG verification (2026-10-20): **158 backend tests and 7 Playwright tests
passed**, including the opt-in actual-backend case. Frontend lint and production
build also passed before this update was pushed.
The discovered ambiguous antiderivative MCQs have been corrected; regression gates
reject the original faulty options before grading. Lint and production build are
checked separately. Coverage includes authentication,
ownership, transactions, migration, validation, MCQ conflicts, OCR failures,
and benchmark manifests. Playwright requires installed Google Chrome and
uses API fixtures for UI regression plus an opt-in real local backend RAG test.
Set `RUN_LOCAL_API_E2E=1` with an isolated backend on port 8002 to include that test.
Without the flag, the real-backend case is skipped. Use a disposable database,
simulation mode and disabled external calls; never test against personal records.
Backend unit tests also isolate data, disable dense loading and block external
HTTP. They do not establish actual GPU operation; the local retrieval and course
workflow scripts separately exercise the cached model.
The Course Library at `/knowledge` supports browsing and hybrid search. Authenticated
administrators can preview, save drafts, publish reviewed material and withdraw
sources, with version checks and archived history. The progress report also includes
rule-based 3/7/14-day review reminders. See [local RAG setup and administration](docs/LOCAL_RAG.md).
These tests do not verify live provider availability or educational effectiveness.

The isolated student simulation now runs four learner profiles across all 13 topics
and three question types: 156 curriculum exercises plus four graded adaptive
follow-ups. It verifies citations, exact progress updates, retry deduplication and
review scheduling. Run `.\.venv\Scripts\python.exe scripts/simulate_students.py`
to regenerate `reports/rag_student_simulation.json` without paid model calls.

An additional [manual teaching-feedback review](reports/rag_manual_mentor_evaluation.md)
covers 13 fixed questions and 52 submissions. It identifies ambiguous MCQs and
evidence gaps; it is not a live DeepSeek benchmark or an independent teaching rating.
The subsequent [remediation report](reports/rag_mentor_remediation.md) records the
fixes and a new 52-case replay. Course notes v1.1 contain 18 knowledge units, with
concept-filtered tutor retrieval and explicit insufficient-evidence handling.

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

## Project demonstration

The recording workflow covers sign-in, incorrect MCQ selection and persistent
highlighting, mentor feedback, source citations, an equivalent correct calculation,
updated learning records, progress charts, recommendations, course search and
Agent Laboratory synthesis. It uses actual browser/API responses, not intercepted
responses.

English voiceover with English subtitles, a silent subtitle version, and Chinese
narration are supported. See [recording instructions](docs/DEMO_VIDEO.md).
The English script focuses on the student's workflow; acceptance metadata retains
actual runtime provenance. Generated videos are not bundled in the Git repository.

Reproduction uses a new isolated session rather than personal accounts:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_demo.py --folder .runtime/demo/my_english_demo
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/demo_voice.ps1 `
  -OutputDirectory .runtime/demo/my_english_demo/voice `
  -NarrationFile data/evaluation/demo_narration_en.json
.\.venv\Scripts\python.exe scripts/render_demo.py --folder .runtime/demo/my_english_demo `
  --audio-info --narration data/evaluation/demo_narration_en.json
$env:DATABASE_URL='sqlite:///.runtime/demo/my_english_demo/demo.db'
$env:OUTPUT_DIR='.runtime/demo/my_english_demo/output'
$env:NEXT_DIST_DIR='.next-e2e'
.\start.ps1 -ApiPort 8003 -WebPort 3103
```

With those services running, use a second terminal from the project root:

```powershell
$env:DEMO_NARRATION='data/evaluation/demo_narration_en.json'
node scripts/record_demo.mjs .runtime/demo/my_english_demo --rehearsal
node scripts/record_demo.mjs .runtime/demo/my_english_demo
.\.venv\Scripts\python.exe scripts/render_demo.py --folder .runtime/demo/my_english_demo
```

Recording requires installed Chrome, Playwright's FFmpeg component, local Windows
speech voices and the isolated `imageio-ffmpeg` rendering dependency. Dependency
setup is documented in the linked guide; it is not part of basic application setup.
Final MP4/SRT/transcripts go to `reports/demo/<session>/`; raw media, the temporary
database and private credentials remain under `.runtime/demo/<session>/`.
Both directories are ignored. Stop the launcher after recording. Sharing a
voiceover video in an online meeting requires sharing computer audio.

## Optional infrastructure profile

`compose.yaml` provides PostgreSQL, an OpenTelemetry Collector, Jaeger, and
Prometheus. These are infrastructure services; start the API and frontend
separately. Keep the text-model settings in your private `.env` and add the
database/telemetry values from [.env.postgres.example](.env.postgres.example):

This retained profile is optional infrastructure, not a requirement for Windows
local use, a containerized application, or an automatic GCP deployment. Its
services are outside the latest local RAG acceptance. Do not expose development
password defaults on a shared host.

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
src/rag/              Hybrid retrieval, ingestion and knowledge-management API
src/learning/         Transactional learning records, receipts and rule planner
src/simulation.py     Parameterized offline teaching fixtures
src/ocr.py            Dedicated vision transcription
src/multi_agent/      Agents, coordinator, message bus, and tools
src/schemas/          Canonical question and API request models
src/validation/       Structural and symbolic validation
src/database/         SQLAlchemy models, repositories, and migration
src/evaluation/       Offline and paired A/B analysis
t2p-web/              Next.js application and browser tests
scripts/              Diagnostics, source tools, simulations, evaluation and recording
data/knowledge/       Versioned original notes and archived manifests
data/evaluation/      Authored review cases and narration scripts
setup.ps1 / start.ps1 Windows local setup and owned-process launcher
tests/                Backend regression tests
docs/                 Interview and production guides
observability/        Collector and Prometheus configuration
reports/              Report snapshots and experiment manifests
```

Private `.env` files, account databases, personal progress, local backups,
generated outputs, and runtime caches are excluded from version control.
Temporary documents and generated recordings are also excluded. A Git pull does
not transfer a local user's password, learning database or demonstration video.

## Troubleshooting

| Symptom | Checks and action |
|---|---|
| Frontend cannot reach API | Check API health, `.runtime/api.stderr.log`, frontend API URL and allowed origins; restart after configuration changes |
| Port in use | Choose different launcher ports; unrelated processes are not stopped |
| CUDA unavailable | Run `scripts/check_environment.py`; inspect driver/PyTorch compatibility and reported CPU fallback reason |
| Keyword-only / missing model | Provision once with `scripts/prepare_rag.py --download`, confirm the cache/revision and restart |
| First request slow | Cached embeddings are loaded on first retrieval; warm the workflow before a presentation |
| HTTP 422 | Read validation details for required fields, password policy, topic/type and request schema |
| Live generation timeout | Check both opt-ins, provider model ID, quota and connectivity; a client timeout does not prove the server never processed a request |
| Photo upload disabled | Expected in simulation; intentional live OCR requires a separate vision provider |
| Typed fixture answer rejected | Enter a final SymPy expression, not a free-form proof |
| Retry does not increase exercise count | Expected: first attempt per question earns credit; duplicate attempt IDs replay safely |
| Admin controls missing | Registration grants student role; change role locally, then sign in again |
| Old source unavailable | Check source version/hash and withdrawal status |
| React DOM errors after translation | Disable browser automatic translation for the app and reload |

The launcher writes API/frontend logs under `.runtime/`. Never publish private
`.env`, access tokens or learner databases in public issues.

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
- Typed calculation/fill-in fixtures have final-expression checks; arbitrary
  live fill-in answers and natural-language proofs do not share those guarantees.
- Difficulty, mastery thresholds, and learning outcomes have not been calibrated
  through a large longitudinal student study; the interview profile is synthetic.
- Password sessions currently use browser session storage; a same-origin
  production deployment can further harden this with Secure HttpOnly cookies.
- Learning updates now come from server-stored submissions, with idempotent retry
  receipts. Only the first attempt on a given problem contributes mastery credit;
  later answers are retained without inflating the exercise count.
- The default AI mode is simulation. Autonomous model quality, open-ended proof
  grading and live provider latency have not been measured in this local RAG run.
- The knowledge base and fixture families are small; held-out retrieval evaluation,
  independent teaching review and longitudinal learning studies remain open.
- Source publication targets a local single-process server; broader deployment
  needs separate concurrency, security and operational verification.
- A clean installation on another Windows machine and the retained optional
  infrastructure require additional environment-specific validation.
- Recharts may emit an initial container-measurement warning during dashboard
  layout; the browser chart-rendering checks pass, but the warning remains.
