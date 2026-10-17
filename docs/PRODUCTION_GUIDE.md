# Calculus Atelier Production Guide

## Authentication

New users register through `POST /auth/register` with a user ID and password.
Passwords use PBKDF2-HMAC-SHA256 with a random per-user salt and a configurable
iteration count. The API returns an opaque 256-bit session token; only its
SHA-256 digest is persisted. Logout revokes the database session.

Progress and result endpoints require `Authorization: Bearer <token>` and
enforce owner-or-admin access. Adaptive generation and user-linked auditing
apply the same ownership rule. Migrated identities do not receive a default
password and therefore cannot be silently claimed. Set one locally with:

```powershell
python manage_user.py set-password EXISTING_USER_ID
```

## PostgreSQL

Install Docker Desktop or provide an existing PostgreSQL 16 service. Copy the
PostgreSQL example variables to a private `.env` file, keeping passwords out of
source control.

```powershell
docker compose up -d postgres
python migrate_legacy_data.py
python api_server.py
```

SQLAlchemy repositories are database-agnostic. SQLite keeps the zero-setup
portfolio experience, while `postgresql+psycopg://...` enables concurrent
deployment. The startup migration upgrades pre-authentication SQLite databases
to schema version 2 without deleting learner data.

## OpenTelemetry

Enable the local observability profile:

```powershell
docker compose up -d jaeger otel-collector prometheus
```

Set:

```text
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
```

The API instruments FastAPI requests, SQLAlchemy queries, outbound HTTPX
requests, request counts and duration, and single-/multi-agent generation
duration. Responses include `X-Request-ID` and, when tracing is active,
`X-Trace-ID`.

- Jaeger traces: `http://127.0.0.1:16686`
- Prometheus metrics: `http://127.0.0.1:9090`

Telemetry never records passwords, session tokens, prompts, or student image
contents.

## Topic-stratified A/B benchmark

Prepare the default 10-topic paired experiment:

```powershell
python ab_benchmark.py prepare
```

Every topic receives 30 cases covering all combinations of five difficulty
levels, three question types, and two modes. Each case is sent to both
pipelines, with pipeline execution order counterbalanced to reduce temporal
provider bias. The default experiment therefore contains 300 matched cases and
600 generation calls.

Live model calls require explicit cost confirmation and support checkpoint
resume:

```powershell
python ab_benchmark.py run --limit 5 --confirm-live-calls
python ab_benchmark.py evaluate
```

The evaluator reports pipeline means, per-topic results, paired differences,
and deterministic 95% bootstrap confidence intervals. Positive deltas favor
multi-agent output except for latency and token use.

## Browser end-to-end testing

The Playwright suite intercepts model-facing API calls with deterministic
fixtures while exercising the real Next.js application in system Chrome.

```powershell
cd t2p-web
npm run test:e2e
```

The test covers registration, bearer propagation, session restoration after
navigation, problem generation, answer auditing, result recording, and the
authenticated progress dashboard. Failure artifacts include screenshots and
traces under `test-results/`.
