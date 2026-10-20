# Windows local RAG implementation

## Scope and truthful demo behavior

Calculus Atelier now has real local hybrid retrieval, published course notes,
source-linked feedback, server-owned progress and explainable recommendations.
CUDA is preferred; CPU fallback is automatic. There is no Docker or GCP dependency.

`AI_MODE=simulation` is the default. `ALLOW_PAID_API=false` blocks paid model
access, even if `.env` already contains keys. The launcher explicitly enforces
these settings. Handwriting OCR is disabled in this mode. A live model is an
optional later integration, not required for development or this verification.

The simulator has parameterized, symbolically checked MCQ, calculation and fill-in
examples for all 13 curriculum topics. It checks a final SymPy expression or
MCQ choice; it does not understand arbitrary handwritten derivations. Exam fixtures
preserve exam mode and hide prompts but explicitly do not measure cross-topic fusion.
Template difficulty is not empirically calibrated.

The agent laboratory uses real message transport, retrieval, scaffolding changes,
validation and storage, with **scripted role replies** in simulation. Its zero LLM
call count must not be presented as autonomous model reasoning or a quality gain.
Live-agent code additionally retrieves purpose-specific evidence before reasoning
and routes drafts through the scaffolder, but it has not been tested against a
paid provider in this change.

## Run on Windows

Requirements: Python 3.10–3.12, Node.js 20.9+, PowerShell, optional NVIDIA hardware.

```powershell
.\setup.ps1 -DownloadModel
.\start.ps1
```

If script execution is restricted, use `powershell -ExecutionPolicy Bypass -File
.\setup.ps1 -DownloadModel` for this invocation rather than changing machine policy.
For an existing workspace with dependencies installed, skip setup and run startup.

The initial free model download requires internet. Runtime retrieval uses only
the local cache. The tested device is GTX 1650 4 GB with PyTorch 2.7.1+cu118.
The model cache was approximately 466 MiB when prepared; package installations,
Next.js build caches and retained backups add separate overhead.

`start.ps1` binds both services to loopback, checks ports, preserves `.env`, makes
a consistent SQLite backup, and stops only processes it owns when interrupted.
Use `-ApiPort 8002 -WebPort 3001` if the defaults are occupied.

The setup script uses `constraints-windows.txt` to constrain the key tested
dependencies and preserves a working CUDA installation. PowerShell scripts have
been syntax checked. The launcher was also exercised with an isolated SQLite
database on ports 8003/3003: both services returned health responses and Ctrl+C
released the ports. A fully
clean-machine dependency installation has not been exercised on a second PC.

## Code boundaries

| Location | Responsibility |
|---|---|
| `src/rag/service.py` | BM25, E5 vectors, RRF, local cache, device fallback, citation allowlist |
| `src/rag/ingestion.py` | Source metadata, explicit publishing, versioned import |
| `src/rag/api.py` | Public course search and administrator-only source publication |
| `t2p-web/src/app/knowledge/page.tsx` | Academic-style course browser and source administration |
| `data/knowledge/calculus.json` | Original notes v1.1, 18 knowledge units across 13 topics; v1.0 archived |
| `src/simulation.py` | Explicit offline teaching and scoring fixtures |
| `src/learning/service.py` | Atomic submission/progress transaction and rule planner |
| `src/database/models.py` | Evidence snapshots and idempotent attempt receipts |
| `scripts/manual_roundtrip.py` | Export an actual prompt and inject a manually authored response |
| `scripts/simulate_students.py` | Isolated student workflow tests and all-topic fixture coverage |
| `scripts/evaluate_rag.py` | Local retrieval development smoke comparison |

## Knowledge administration

Open **Library** in the top navigation, or visit `/knowledge`. All learners can
browse published passages, filter by topic/source and search local course notes.
Worked-example units are excluded from this general browser and search.

Publishing controls require an administrator account; registration never grants
this permission. To grant it to an existing account on your own machine:

```powershell
.\.venv\Scripts\python.exe manage_user.py set-role YOUR_ACCOUNT_ID admin
```

This command backs up the local SQLite database before updating the role. Sign out
and sign in again, then open Library. No personal account was promoted during
implementation. Use `set-role YOUR_ACCOUNT_ID student` to remove the permission.

The administration panel supports preview, save draft, review, publish and withdraw.
Publish only after confirming rights, mathematics and extracted formulas. It checks
the actual local embedding tokenizer's 512-token limit before publication; prepare
the model first if it is unavailable. Files are limited to 5 MB, text PDFs to 50
pages and each import to 100 semantic units. No OCR is performed. Status/content
changes retain the prior manifest; stale writes return 409 instead of overwriting
another change. This is intended for the local single-process server.

The supplied notes are original project reference material, not externally
certified textbook excerpts. Their CC0 metadata applies to these new notes only,
not the whole repository. Review mathematics and course alignment before classroom use.

List sources:

```powershell
.\.venv\Scripts\python.exe scripts/knowledge.py list
```

Import reviewed material you are permitted to use:

```powershell
.\.venv\Scripts\python.exe scripts/knowledge.py import `
  --file D:/course/notes.md --source-id my-course --title "Course notes" `
  --version 1 --topic "Derivatives and Differentiation" `
  --provenance "Original notes by the course author" --license "Private course use"
```

Imports default to draft and are not retrieved. Add `--publish` only after
reviewing rights, extracted formulas and content. Markdown/text, structured JSON
and text-readable PDF are supported. PDF needs `pypdf`; scanned PDFs need separate
OCR and are rejected if no text is extracted. Oversized sections are rejected
instead of silently cutting formulas. Publishing long units also requires checking
the embedding tokenizer length. No public upload endpoint accepts arbitrary URLs.

Change the version when editing published content. Earlier manifests are archived
outside the active catalog. Set a source's status to `withdrawn` to stop new
retrieval. Feedback stores its evidence snapshot; a source dialog checks the
content hash and reports when the active version has changed or been withdrawn.
Generated questions do not automatically become trusted course knowledge.

## Submission and recommendation integrity

`/generate` returns a learner DTO without solution, answer key, expected expression,
symbolic answer claims or full internal evidence. Agent events also redact problem
payloads. The stored exam mode controls restrictions even if a request says drill.

`/audit` accepts an `attempt_id`. A transaction saves the submission, evidence
snapshot, mastery change and retry receipt. Reusing the ID with the same payload
returns the original response; changing the payload produces 409. The retired
`/user/record` returns 410 rather than trusting client-provided scores.

Only the first attempt on a particular question updates mastery. Later attempts
remain visible as submissions without extra exercise credit. The EMA baseline
remains 0.4 old + 0.6 current; it is not a calibrated knowledge-tracing model.
Promotion requires several recorded independent attempts. Recommendations use
topic performance, recent error evidence and reviewed prerequisite links.
Concept IDs are recorded with receipts and the progress report shows observed
first-attempt accuracy, explicitly labeling small samples. Repeated weak concept
evidence can increase recommendation priority. A single wrong choice never establishes
a particular misconception. The report's review queue uses a transparent rule:
after at least three independent recorded exercises and a latest correct answer
scoring at least 80, schedule review after 3 days, or 7/14 days after at least
3/5 consecutive correct attempts. Only due items appear. Malformed/future timestamps
are excluded. Overdue practice can raise recommendation priority without overriding
more urgent foundational gaps. This is not a fitted forgetting model; a calibrated
concept mastery model remains a future extension.

## Manual assistant roundtrip without an API

```powershell
.\.venv\Scripts\python.exe scripts/manual_roundtrip.py --prepare
```

This exports `.runtime/manual-review/request.json`, containing the actual mentor
prompt, full options, deterministic assessment and retrieved evidence. A person
or assistant reads it and writes a JSON response to a separate file. Then run:

```powershell
.\.venv\Scripts\python.exe scripts/manual_roundtrip.py --response path/to/response.json
```

The response is injected through a test adapter into the regular `/audit` path,
using a separate SQLite database. It is not a persistent chat-to-backend API.
One real request was reviewed in this development session: the incorrect option
added 1 to the derivative of `(3*x+1)**3`. The authored feedback cited the chain
rule, preserved the backend's zero score, and avoided diagnosing a misconception
from one selected option. See `reports/rag_manual_roundtrip.json`.

A subsequent manual assistant review covers 13 fixed questions and 52 submissions.
Run `scripts/evaluate_manual_mentor.py --prepare`, read the packet, then replay
`--responses data/evaluation/manual_mentor_reviews.json`. See
`reports/rag_manual_mentor_evaluation.md` for method, findings and limitations.
The review found ambiguous antiderivative MCQs and a marginal-cost evidence gap;
the baseline reports are retained. The subsequent remediation changes the distractors,
adds semantic option checks and notes v1.1, and replays all 52 cases into
`reports/rag_mentor_remediation.json`. See `reports/rag_mentor_remediation.md` for the
before/after comparison. No live model was used; authored feedback replay is still
not independent teaching evaluation.

New MCQs require `option_expressions`, a symbolic claim, an equivalence policy and
explicit finite excluded points. Checked expressions must match the canonical LaTeX
shown in the options, preserving unsimplified domain holes. Only one option may
match the reference, including constant-shift equivalence for indefinite integrals.
The generator, agent review/save and grading paths reject failed checks. Legacy
MCQs without this metadata are explicitly unverified/partial, not silently certified;
known antiderivative questions lacking the metadata require review before grading.
Arbitrary prose, tuple-valued options and domains needing richer interval constraints
are outside this scalar symbolic gate and require manual review. Existing personal
questions/data were not rewritten.

Tutor retrieval filters by the problem's concept tags when present; no matching
concept means insufficient evidence, not a fallback to unrelated same-topic notes.
An explicit `evidence_insufficient=true` reply suppresses citations. This coarse
filter and valid-ID checks do not prove semantic claim support, so
`support_status=not_independently_verified` remains truthful.

## Verification and reports

```powershell
.\.venv\Scripts\python.exe -m pytest tests
.\.venv\Scripts\python.exe scripts/simulate_students.py
.\.venv\Scripts\python.exe scripts/evaluate_rag.py
.\.venv\Scripts\python.exe scripts/verify_course_workflow.py
cd t2p-web
npm.cmd run lint
npm.cmd run build
```

For browser testing, start an **isolated** offline backend on port 8002, then:

```powershell
$env:RUN_LOCAL_API_E2E='1'
npm.cmd run test:e2e
```

The UI tests use port 3100 with an independent `.next-e2e` directory. API fixtures
exercise registration, progress and modal behavior. An additional real-backend
test generates a question, submits a typed expression and opens its actual source.
Do not run that test against a personal database.

Latest verification: **158 backend tests and 7 Chromium browser tests passed**.
The original ambiguous MCQs are now negative regression cases: the gate must reject
them. The frontend is unchanged; lint and production build passed in its preceding
verification. First retrieval loads the cached model and can be slower
than later requests; the real-backend browser test separately checks the generation
response and subsequent rendering, with a bounded cold-start wait.

Reports:

- `reports/rag_student_simulation.json`: four synthetic profiles, each practicing all
  13 topics over MCQ/calculation/fill-in rounds: 156 curriculum exercises plus four
  graded adaptive follow-ups. Checks include exact per-topic EMA/count/level changes,
  160 same-ID replays, 52 fresh-ID retries with no extra credit, resolvable course
  citations, answer-key redaction, and recommendations matching actual next questions.
  An eight-day clock projection checks review eligibility without editing timestamps.
  The report also retains two scripted-role problems and 39 anonymous topic/type
  generation-and-scoring checks. The four complete profiles are regression tests in
  `tests/test_student_simulation.py`, with external HTTP blocked during pytest.
- `reports/rag_retrieval_smoke.json`: keyword versus hybrid retrieval over a small
  development set, including out-of-scope queries and warm latency.
- `reports/rag_manual_roundtrip.json`: one manually authored response through the API.
- `reports/rag_manual_mentor_evaluation.json` and `.md`: 52 personally authored
  reviews replayed through the API, symbolic evidence for ambiguous MCQs, citation
  coverage findings, and explicit separation from independent/live model evaluation.
- `reports/rag_mentor_remediation.json` and `.md`: post-fix 52-case replay,
  before/after findings, definition-domain and new-parameter regression scope.
- `reports/rag_course_workflow.json`: actual local CUDA publishing/retrieval/withdrawal,
  student permission denial, stale-write protection and version archival using a
  separate database and source catalog, with zero paid API calls.

The retrieval set was authored alongside the notes and is **not held out**. Its
results cannot establish general superiority or real student learning gains.
The relevance threshold is a development heuristic, not a correctness probability.
Citation existence is checked; claim support is labeled as not independently
verified. Larger blinded evaluation and paid-model A/B runs were deliberately not
performed. Real DeepSeek quality, latency and cost therefore remain unmeasured.

## Data safety and remaining scope

The existing SQLite database was backed up before implementation. Simulators and
pytest use separate databases and do not change `student_01`. Schema v3 adds tables
without deleting existing records. `.env` and user passwords were not changed.

Remaining work before claiming a classroom-ready product includes a larger
reviewed knowledge base, held-out retrieval and teaching evaluation, broader
mathematical verification, real learner studies, and validating setup on another
Windows machine. A browser warning about initial Recharts dimensions can still
appear during layout measurement; existing chart rendering assertions pass.
