# Calculus Atelier

Calculus Atelier is an adaptive calculus learning system that combines structured LLM
generation, handwritten-solution auditing, deterministic mathematics checks,
and multi-agent dataset curation.

The project is designed around one principle: language models may create and
review educational content, but they must not be the only authority on
machine-checkable mathematics.

## What the system does

- Generates drill and integrated-exam calculus problems.
- Supports calculation, multiple-choice, and fill-in formats.
- Uses a curated 252-problem dataset for examples and topic coverage.
- Transcribes handwritten work and provides step-level tutor feedback.
- Tracks topic mastery and recommends the next learning task.
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
Prompt + RAG examples      Synthesizer / Scaffolder
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
       SQLite + inspectable JSON artifacts
                   |
       OCR and AI mentor auditing
```

### Quality states

Generated content is never auto-approved when a reviewer fails. A problem may
be:

- `passed`: schema and symbolic claim both passed.
- `partial`: schema and invariants passed, but no honest symbolic claim applies.
- `validation_failed`: deterministic checks found an error.
- `review_failed`: the quality reviewer did not produce a reliable verdict.
- `approved`: deterministic validation and pedagogical review passed.

## Technology

- Backend: Python, FastAPI, Pydantic, SymPy, SQLAlchemy
- Persistence: SQLite locally or PostgreSQL for multi-user deployment
- Observability: OpenTelemetry, Jaeger, and Prometheus
- AI integration: DeepSeek text reasoning plus a dedicated OpenAI-compatible vision OCR API
- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS
- Mathematics: KaTeX and SymPy
- Visualization: Recharts and Matplotlib
- Testing: pytest

## Quick start

### 1. Configure the backend

Copy `.env.example` to `.env`, then configure the text grading model. To enable
photo and handwritten review, also configure a separate vision-capable model:

```dotenv
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro

VISION_PROVIDER=openai-compatible
VISION_API_KEY=your-vision-provider-key
VISION_BASE_URL=https://api.openai.com/v1
VISION_MODEL=your-vision-capable-model
```

`VISION_MODEL` must accept OpenAI-compatible `image_url` message content. The
backend reports the effective, non-secret configuration at `/capabilities`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api_server.py
```

The API runs at `http://127.0.0.1:8001`. Interactive API documentation is
available at `/docs`.

### 2. Start the frontend

```powershell
cd t2p-web
npm install
npm run dev
```

Open `http://localhost:3000`.

### Photo review architecture

Photo submissions use a strict two-model pipeline:

```text
JPEG / PNG / WebP (maximum 5 MB)
    -> dedicated vision OCR provider
    -> faithful LaTeX/text transcript
    -> DeepSeek V4 Pro text-only grading
    -> structured score and tutor feedback
```

Images are never sent to DeepSeek. If vision OCR is missing or fails, the API
returns `VISION_OCR_NOT_CONFIGURED` or `VISION_OCR_FAILED`; it does not silently
invent a transcript or fall back to an incompatible text model. The frontend
shows the current capability state and disables photo submission until the
vision provider is ready.

### 3. Migrate existing project data

The migration is idempotent: it can be run repeatedly and does not delete or
rewrite the original JSON files.

```powershell
python migrate_json_to_sqlite.py
```

SQLite is the runtime source of truth for users, topic mastery, learning
events, generated problems, submissions, and generation runs. JSON remains an
inspectable generation artifact. Set `MIRROR_JSON_PROGRESS=true` only when an
older integration still needs progress-file mirrors.

### 4. Restore the interview demo record

The existing `student_01` account can be restored to a deterministic B-grade calculus
record before an interview demonstration:

```powershell
python -m scripts.seed_student_demo
```

The command creates an online SQLite backup in `data/backups/`, then replaces
only this account's mastery and learning-event history. It is safe to run more
than once, does not change the account password, and produces an 84% average
mastery profile with 62 completed exercises, a clear differential-calculus
strength, and one concrete next priority.

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

## API overview

| Method | Route | Purpose |
|---|---|---|
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

## Verification

Run backend tests:

```powershell
pytest
```

Run the frontend production check:

```powershell
cd t2p-web
npm run build
npm run test:e2e
```

Generate the reproducible single-agent versus multi-agent comparison:

```powershell
python evaluate_system.py
```

This produces `reports/evaluation_report.json`,
`reports/evaluation_report.md`, and a fixed 100-case
`reports/benchmark_tasks.json` manifest. The offline analysis performs no paid
model calls; the task manifest can also be used for a controlled live A/B run.

Prepare the fully paired, topic-stratified A/B experiment:

```powershell
python ab_benchmark.py prepare
```

The default manifest contains 300 cases across 10 topics and 600 paired
generation calls. Live execution requires the explicit
`--confirm-live-calls` flag because it can consume substantial model quota.

## Production profile

`compose.yaml` provides PostgreSQL, an OpenTelemetry Collector, Jaeger, and
Prometheus. Copy `.env.postgres.example` to a private environment file, then:

```powershell
docker compose up -d
python migrate_legacy_data.py
python api_server.py
```

Jaeger is available at `http://127.0.0.1:16686` and Prometheus at
`http://127.0.0.1:9090`. See `docs/PRODUCTION_GUIDE.md` for authentication,
database, observability, benchmark, and E2E details.

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
- Password sessions currently use browser session storage; a same-origin
  production deployment can further harden this with Secure HttpOnly cookies.
