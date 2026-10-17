# T2P: A Multi-Agent Collaborative System for Calculus Pedagogical Data Synthesis

## Academic Project Report (English Version)

---

**Abstract**

This report presents T2P (Term 2 Project) — an AI-driven data synthesis system for calculus education. Built around the core objective of "Data Synthesis for Enhancing Mathematical Learning with Pedagogical Principles," the system implements three primary functional modules: (1) automated calculus problem generation via large language models, supporting both drill practice and multi-concept fusion examination modes; (2) an intelligent auditing engine featuring handwriting OCR recognition and Socratic tutorial feedback; and (3) a genuine multi-agent collaborative system based on message-passing architecture, wherein four autonomous agents (ProblemSynthesizer, ScaffoldingDesigner, QualityReviewer, and DatasetCurator) collaborate concurrently through an asynchronous message bus to produce high-quality, coverage-balanced mathematical problem datasets. The backend is built on FastAPI, the frontend employs Next.js 16 and React 19, and the language model service is provided by DeepSeek V4 Pro. Experimental results demonstrate that, compared to the traditional pipeline architecture, the message-driven multi-agent system reduces the number of LLM calls per problem from 8–10 to 4–5 while enabling emergent collaboration patterns among agents.

**Keywords**: Multi-agent systems; large language models; mathematics education; data synthesis; message-passing architecture; calculus instruction

---

## 1. Introduction

### 1.1 Background

Calculus constitutes a cornerstone course in higher education across science and engineering disciplines. However, its instruction faces two fundamental challenges. First, there exists a scarcity of high-quality practice problems — traditional problem banks are constrained by manual authoring throughput and cannot readily cover diverse difficulty levels and inter-concept combinations. Second, personalized feedback remains elusive — in large-enrollment classrooms, instructors cannot provide per-problem grading and targeted guidance to every student. Recent breakthroughs in large language models (LLMs) for mathematical reasoning have established a technological foundation for automated problem generation and intelligent grading. Nevertheless, a single LLM invocation exhibits significant limitations in mathematical correctness, pedagogical appropriateness, and logical coherence.

Multi-agent systems (MAS) offer a new paradigm for addressing these challenges through role specialization and collaborative mechanisms. Multiple specialized AI agents can respectively assume responsibility for problem creation, quality assurance, pedagogical scaffolding design, and global curation, achieving collaborative intelligence that surpasses that of any single LLM through structured communication protocols.

### 1.2 Objectives

This research aims to design and implement the T2P system with the following objectives:

1. **Automated problem generation**: Support drill mode (single-concept) and exam mode (multi-concept fusion), covering calculation, multiple-choice, and fill-in-the-blank question types, with configurable difficulty (levels 1–5).
2. **Intelligent auditing engine**: Accept student handwritten image inputs, perform OCR transcription, and conduct step-by-step logical evaluation, providing Socratic tutorial feedback rather than binary correct/incorrect judgments.
3. **Genuine multi-agent data synthesis**: Construct a message-passing-based autonomous multi-agent system enabling direct inter-agent communication, autonomous decision-making, and concurrent collaboration.
4. **Adaptive learning pathways**: Implement exponential moving average (EMA) based mastery tracking for automatic difficulty and mode adjustment.

### 1.3 Report Structure

The remainder of this report is organized as follows. Section 2 reviews related work. Section 3 describes the system architecture in detail. Section 4 elaborates on the multi-agent system design. Section 5 presents the problem generation and evaluation methodology. Section 6 addresses the frontend interaction design. Section 7 provides system evaluation results. Section 8 offers a discussion. Section 9 concludes and outlines future work.

---

## 2. Related Work

### 2.1 Large Language Models in Mathematics Education

LLMs such as GPT-4, Claude, and DeepSeek have demonstrated remarkable capabilities in mathematical reasoning tasks (OpenAI, 2023; Anthropic, 2024). Benchmarks including MathQA (Amini et al., 2019) and GSM8K (Cobbe et al., 2021) indicate that state-of-the-art models achieve competitive accuracy on structured mathematical problems. However, these models still face challenges when generating instructionally appropriate mathematical content: reliable LaTeX formatting, complete logical correctness in derivations, and pedagogical appropriateness remain problematic.

In the educational domain, Khan Academy's Khanmigo platform has demonstrated the potential of LLMs as AI tutors. Du et al. (2024) proposed the MathVC framework, which employs multi-agent discussion to verify mathematical reasoning — an approach that inspired the quality control mechanisms in our system.

### 2.2 Multi-Agent Systems and Educational Content Generation

Multi-agent systems have advanced significantly in content generation. ChatDev (Qian et al., 2023) simulates the organizational structure of a software company, generating code through role-playing. AutoGen (Wu et al., 2023) provides a general-purpose multi-agent conversation framework. In education, Park et al. (2024) used multi-agent simulation of teacher-student interactions to generate training data.

However, existing research shares common limitations: (1) most systems employ hardcoded pipeline orchestration, with no genuine direct communication among agents; (2) agent LLM calls often exhibit a two-layer waste pattern — the agent invokes an LLM solely for tool routing, and the tool internally invokes another LLM for the actual work; (3) specialized evaluation dimensions for mathematics education are lacking.

The T2P system addresses these limitations through a message-bus-based genuine multi-agent communication architecture.

### 2.3 Scaffolding Theory

Scaffolded instruction originates from Vygotsky's (1978) Zone of Proximal Development (ZPD) theory, which emphasizes providing progressive hints at appropriate difficulty levels to guide learners. T2P embeds this principle into the structural design of every problem — progressing from conceptual hints (Step 1: what principle applies?) to strategic hints (Step 2: what approach to take?) to procedural hints (Step 3: the first calculation step) to verification hints (Step 4: how to verify your answer), forming a complete cognitive guidance chain.

---

## 3. System Architecture

### 3.1 Overall Architecture

The T2P system adopts a separated frontend-backend architecture, illustrated in Figure 1.

```
┌──────────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 16 + React 19)              │
│                      Port 3000 (Tailwind CSS v4)                  │
│  ┌──────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │ Generation   │  │ Handwriting      │  │ Multi-Agent Live    │ │
│  │ Panel        │  │ Audit Canvas     │  │ Monitor (SSE Stream)│ │
│  └──────────────┘  └──────────────────┘  └─────────────────────┘ │
│  ┌──────────────┐  ┌──────────────────┐                          │
│  │ Problem View │  │ Dashboard        │                          │
│  │ (LaTeX)      │  │ (Radar + Bar)    │                          │
│  └──────────────┘  └──────────────────┘                          │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP/REST + SSE
┌──────────────────────────▼───────────────────────────────────────┐
│                    Backend (FastAPI + Uvicorn)                    │
│                        Port 8001 (Python 3.x)                     │
│  ┌───────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │ /generate     │  │ /audit         │  │ /synthesize-v2     │   │
│  │ (Generation)  │  │ (Auditing)     │  │ (Multi-Agent Synth)│   │
│  └───────┬───────┘  └───────┬────────┘  └─────────┬──────────┘   │
│          │                  │                      │              │
│  ┌───────▼───────┐  ┌───────▼────────┐  ┌─────────▼──────────┐   │
│  │ BatchGenerator│  │ LLMClient      │  │ Coordinator        │   │
│  │ → Generator   │  │ .mentor_review │  │ → MessageBus       │   │
│  │ → Evaluator   │  │ OCRClient      │  │ → 4 Autonomous     │   │
│  │ → PostProcessor│ │                │  │   Agents (async)    │   │
│  └───────────────┘  └────────────────┘  └────────────────────┘   │
│                           │                                       │
│                  ┌────────▼────────┐                              │
│                  │ DeepSeek V4 Pro │                              │
│                  │ (OpenAI-compat.)│                              │
│                  └─────────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Backend Components

#### 3.2.1 API Server (api_server.py)

The FastAPI application exposes 10 endpoints:

| Method | Endpoint | Function |
|--------|----------|----------|
| GET | `/` | Service status and dataset information |
| GET | `/topics` | Retrieve available topic list |
| POST | `/user/login` | User login and session creation |
| GET | `/user/progress/{user_id}` | Retrieve learning progress data |
| POST | `/user/record` | Record a learning outcome |
| POST | `/generate` | Generate problems (supports adaptive mode) |
| POST | `/audit` | Intelligently audit student submissions |
| POST | `/synthesize` | Legacy multi-agent pipeline (V1) |
| POST | `/synthesize-v2` | New multi-agent synthesis (V2) |
| GET | `/synthesize-v2/stream` | Multi-agent real-time SSE stream |

#### 3.2.2 Problem Generation Pipeline (generator.py + batch_generator.py)

`ProblemGenerator` implements a generation loop with self-healing feedback:

1. **Prompt construction** (PromptBuilder): Builds specialized prompts based on mode (drill/exam), difficulty, and question type, injecting LaTeX formatting constraints and logical correctness requirements.
2. **LLM invocation** (LLMClient): Calls DeepSeek V4 Pro via the OpenAI-compatible interface.
3. **Post-processing** (PostProcessor): JSON parsing, LaTeX sanitization, field normalization.
4. **Quality evaluation** (QualityEvaluator): Structural validation + AI deep semantic audit + originality check.
5. **Self-healing retry**: Upon evaluation failure, AI feedback is injected into the next-round prompt.

`BatchGenerator` handles batch scheduling, including anchor rotation (exam mode), dynamic temperature control, and semantic deduplication.

#### 3.2.3 Intelligent Auditing Pipeline (api_server.py audit endpoint)

1. **Input parsing**: Detect base64 image or plain text.
2. **OCR transcription** (OCRClient): Use DeepSeek Vision model to recognize handwritten LaTeX.
3. **Problem retrieval**: Search across both golden dataset and generated output directory.
4. **Mentor review** (LLMClient.mentor_review): Step-by-step logical comparison with error analysis and Socratic guidance.
5. **Score calibration**: Different calibration strategies for MCQ vs. open-ended responses.

#### 3.2.4 User Learning Management (user_session.py)

`UserSession` implements adaptive learning pathways:

- **EMA mastery algorithm**: `new_mastery = old_mastery × 0.4 + (score/100) × 0.6`
- **Level promotion**: L1 (Basic) → L2 (Scaffolded) → L3 (Exam Ready), threshold at score ≥ 80.
- **Adaptive task parameters**: Iterates roadmap in order, finds the first topic with mastery < 85%.

### 3.3 Frontend Architecture

The frontend is built on Next.js 16.2.4, React 19.2.4, and Tailwind CSS v4.

**Primary pages**:
- **Home page (page.tsx)**: Problem generation configuration panel, LaTeX-rendered problem display area, handwriting signature canvas with image upload, scaffold hint expand/collapse, audit result display, multi-agent synthesis panel.
- **Dashboard (dashboard/page.tsx)**: Radar chart showing per-topic mastery percentages, bar chart showing per-topic level vs. practice count.

**Key dependencies**: KaTeX (math rendering), react-signature-canvas (handwriting canvas), Recharts (charts), axios (HTTP client).

---

## 4. Multi-Agent System Design

### 4.1 Design Motivation

Traditional multi-agent implementations (exemplified by this project's V1 system) exhibit the following structural deficiencies:

1. **Hardcoded pipeline**: The orchestrator invokes agents in a fixed order; agents have no autonomous decision-making authority.
2. **No direct communication**: Agents pass state only through a shared dictionary (workspace); there is no message routing mechanism.
3. **Two-layer LLM waste**: An agent invokes an LLM solely to decide "which tool should I call?", and the tool internally invokes another LLM for the actual work.
4. **Serial execution**: Agents run sequentially with no concurrency capability.

The T2P V2 system undertakes a fundamental restructuring to address these issues.

### 4.2 Message Protocol Design

The system defines a structured message protocol (messages.py) serving as the universal language for inter-agent communication:

| Message Type | Semantics | Sender Example | Receiver Example |
|-------------|-----------|----------------|-----------------|
| `REQUEST` | Request task execution | Coordinator → Synthesizer | "Generate a derivative problem" |
| `RESPONSE` | Return task result | Synthesizer → Reviewer | "Problem ready for review" |
| `APPROVE` | Approval | Reviewer → Synthesizer | "Quality met, approved" |
| `REJECT` | Rejection with revision suggestions | Reviewer → Synthesizer | "Rejected: integration step incorrect" |
| `DELEGATE` | Delegate subtask | Reviewer → Scaffolder | "Design scaffolding for this problem" |
| `CONSULT` | Request consultation | Curator → Synthesizer | "Suggest generating an integral problem" |
| `NOTIFY` | Status notification | Reviewer → Curator | "A derivative problem was approved" |
| `BROADCAST` | Global announcement | Curator → ALL | "Dataset is complete" |

Each `Message` contains: `id`, `type`, `sender`, `recipient`, `conversation_id`, `content`, `timestamp`, and `reply_to`, enabling the construction of complete conversation threads.

### 4.3 Message Bus (MessageBus)

The `MessageBus` is the core infrastructure enabling asynchronous inter-agent communication:

- **Registration mechanism**: Each agent receives a dedicated `asyncio.Queue` inbox.
- **Point-to-point routing**: `send(message)` delivers to the target queue based on the `recipient` field.
- **Broadcast mechanism**: When `recipient=None`, the message is broadcast to all registered agents.
- **Conversation tracking**: Maintains a global mapping of `conversation_id → Conversation`.
- **Thread safety**: Uses `asyncio.Lock` to ensure data consistency under concurrency.

### 4.4 Autonomous Agent Architecture

Each `AutonomousAgent` runs an independent Perceive-Think-Act loop:

```
while self.running:
    1. PERCEIVE: messages = await bus.drain(agent_id)
       - Read all pending messages from inbox
       - Update agent memory (last 50 history entries)

    2. THINK: action = await self._reason(messages)
       - Build reasoning prompt: role + personality + memory context + new messages
       - Invoke LLM to decide next action
       - Output structured Action (SEND_MESSAGE | CALL_TOOL | WAIT | FINISH | BROADCAST)

    3. ACT: await self._act(action)
       - SEND_MESSAGE: Send message to target agent (content generated directly by LLM)
       - CALL_TOOL: Invoke pure utility function (file I/O, data lookup)
       - BROADCAST: Broadcast to all agents
       - WAIT: Idle wait
       - FINISH: End execution
```

**Key innovation**: The LLM directly produces complete content (problem JSON, evaluation reports, scaffolding hints, etc.) in its response, rather than first invoking an LLM for a routing decision and then calling a tool that invokes a second LLM. This eliminates more than half of all LLM calls.

### 4.5 Four Agent Role Definitions

| Agent | ID | Role | Temperature | Max Idle | Tools |
|-------|-----|------|-------------|----------|-------|
| ProblemSynthesizer | synthesizer | Creative Mathematician | 0.5 | 120s | save_problem, get_topics, get_examples |
| ScaffoldingDesigner | scaffolder | Patient Teacher | 0.3 | 60s | get_topics, get_examples |
| QualityReviewer | reviewer | Rigorous Auditor | 0.2 | 120s | check_coverage, get_topics, save_problem |
| DatasetCurator | curator | Strategic Planner | 0.3 | 180s | check_coverage, get_topics, get_examples, get_dataset_size, save_problem |

**ProblemSynthesizer**: Upon receiving a generation request, the LLM directly outputs a complete problem JSON (including problem statement, solution, scaffolding hints, and integration analysis), then sends it to the Reviewer for quality inspection.

**ScaffoldingDesigner**: When the Reviewer or Synthesizer delegates a scaffolding design task, the LLM directly generates a progressive hint sequence (2 steps for difficulty 1–2, 3 steps for difficulty 3, 4 steps for difficulty 4–5).

**QualityReviewer**: Upon receiving a problem for review, the LLM directly evaluates it across six dimensions (mathematical correctness, logical coherence, pedagogical value, difficulty calibration, scaffolding quality, LaTeX formatting) and issues APPROVE or REJECT (with specific revision suggestions), simultaneously notifying the Curator.

**DatasetCurator**: Monitors the count of approved problems, analyzes topic coverage gaps, sends next-topic suggestions to the Synthesizer, and broadcasts a `dataset_complete` termination signal upon reaching the target count.

### 4.6 Coordinator

The `Coordinator` is a lightweight session manager that does not control agent decision-making:

1. Creates the MessageBus and four agent instances.
2. Concurrently launches all agents via `asyncio.gather()`.
3. Sends an initial generation request to the Synthesizer and configuration notifications to the Reviewer and Curator.
4. Polls the message bus every 2 seconds, detecting the `dataset_complete` broadcast or timeout.
5. Sends a stop signal, collects all saved problems, and computes statistics.
6. Outputs the complete dataset and multi-agent conversation log.

### 4.7 LLM Call Efficiency Comparison

| Phase | V1 Pipeline (per problem) | V2 Message System (per problem) |
|-------|---------------------------|--------------------------------|
| Synthesizer agent routing LLM | 1 | 0 |
| generate_problem tool → LLM | 1 | 0 |
| Synthesizer direct generation | 0 | 1 |
| Scaffolder agent routing LLM | 1 | 0 |
| design_scaffolding tool → LLM | 1 | 0 |
| Scaffolder direct generation (on-demand) | 0 | 0–1 |
| Reviewer agent routing LLM | 1–2 | 0 |
| evaluate_quality tool → LLM | 1 | 0 |
| Reviewer direct evaluation | 0 | 1 |
| Curator agent routing LLM | 1 | 1 |
| **Total** | **8–10** | **4–5** |

For a dataset of 20 problems (with approximately 20% rejection rate), V2 saves approximately 100–120 LLM calls.

---

## 5. Problem Generation and Evaluation Methodology

### 5.1 Prompt Engineering

`PromptBuilder` implements a sophisticated prompt construction strategy:

**Base role assignment**: Drill mode employs "Calculus Pedagogy Researcher"; exam mode employs "Senior Mathematics Curriculum Designer (Fusion Specialist)."

**Logical integrity constraints**:
- Numerical verification: critical numerical results must be independently verifiable.
- Geometric consistency: descriptions involving graphics must be self-consistent.
- LaTeX compliance: high-risk macros such as `\quad` are prohibited; only `$` and `$$` delimiters are permitted.

**Output structure**:
```json
{
  "id": "T2P_GEN_1",
  "topic": "Derivatives and Differentiation",
  "problem_statement": "LaTeX problem statement",
  "question_type": "calculation",
  "difficulty": 3,
  "solution": "Detailed multi-step LaTeX solution",
  "scaffolding": [
    {"step": 1, "hint": "Conceptual hint for the first hurdle"},
    {"step": 2, "hint": "Strategic hint for the approach"}
  ],
  "integration_analysis": "Analysis of cross-concept integration (exam mode only)"
}
```

**Self-healing feedback injection**: When quality evaluation fails, AI feedback is formatted as a "Previous Attempt Flaw" block and injected into the next-round prompt.

### 5.2 Quality Evaluation Framework

`QualityEvaluator` implements a multi-dimensional quality assessment framework:

**Evaluation dimensions and weights**:

| Dimension | Weight | Assessment Content |
|-----------|--------|-------------------|
| Mathematical Logic | 0.35 | Mathematical correctness of solution; presence of reasoning errors |
| Structural Completeness | 0.10 | Whether required fields are present |
| Scaffolding Quality | 0.15 | Progressiveness and guiding effectiveness of hints |
| Pedagogical Alignment | 0.15 | Whether difficulty matches; suitability for instructional objectives |
| Concept Integration | 0.15 | Quality of cross-concept connections (exam mode emphasis) |
| Originality | 0.10 | Text similarity to golden dataset |

**Pass thresholds**:
- Drill mode: total ≥ 60, mathematically correct, logically coherent, structure ≥ 75.
- Exam mode: same as drill plus concept integration ≥ 50.

### 5.3 Post-Processing Pipeline

`PostProcessor` implements an eight-step LaTeX deep cleaning pipeline:

1. Unify delimiter formats (`\( \)` → `$`, etc.)
2. Repair residual escape characters
3. Clean LaTeX environment spacing
4. Remove extraneous `$` inside `{cases}` environments
5. Anti-repetition detection (formula duplication removal)
6. Remove prohibited macros (`\quad`, `\qquad`, etc.)
7. Add spacing between mathematical formulas and non-Latin characters
8. Final trimming

Deduplication uses the `paraphrase-multilingual-MiniLM-L12-v2` sentence-transformers model for semantic cosine similarity detection (threshold 0.85).

---

## 6. Frontend Interaction Design

### 6.1 Problem Generation Interaction

Users configure four parameters through a control panel: topic (dropdown selection), mode (drill/exam), difficulty (1–5 slider), and question type (MCQ/fill-in/calculation). Upon clicking "Generate current configuration question," the frontend fetches a problem via `POST /generate` and renders it in the display area.

### 6.2 Handwriting Audit Interaction

Student submissions support three input modalities:
1. **Handwriting signature canvas**: Write directly on screen using react-signature-canvas.
2. **Photo upload**: Upload handwritten images via camera or file picker.
3. **Direct input**: Click an option button for MCQ responses.

After submission, the frontend calls `POST /audit`. The returned result includes: correctness determination, logic alignment score (visualized as a progress bar), error analysis, tutor feedback, and next-step hint.

### 6.3 Multi-Agent Real-Time Monitoring Panel

The newly added multi-agent synthesis panel provides:
- Topic multi-select tags
- Count and difficulty sliders
- Mode/type toggles
- "Start Multi-Agent Synthesis" button

During execution, SSE (Server-Sent Events) streams the agent conversation in real time:
```
[synthesizer] → [reviewer]  [request]  {"action": "review_problem", ...}
[reviewer] → [synthesizer]  [approve]  {"score": 87, "passed": true, ...}
[curator] → [synthesizer]   [consult]  {"action": "suggest_topic", ...}
```

Upon completion, statistics cards display: number of generated problems, LLM call count, agent message count, duration, topic coverage, and average quality score.

### 6.4 Learning Dashboard

The dashboard retrieves user data via `GET /user/progress/{user_id}` and renders using Recharts:
- **Radar chart**: Displays mastery percentages across all topics.
- **Bar chart**: Compares per-topic level and practice counts.

---

## 7. System Evaluation

### 7.1 Functional Verification

| Test Item | Method | Result |
|-----------|--------|--------|
| Frontend-backend connectivity | Start backend → load frontend page → GET /topics | HTTP 200, topic list correct |
| Problem generation (drill) | POST /generate {drill, difficulty=3} | Returns complete problem JSON with scaffolding |
| Problem generation (exam) | POST /generate {exam, difficulty=4} | Returns fusion problem with non-empty integration_analysis |
| Handwriting audit | POST /audit {base64 image + problem_id} | Returns OCR text + logic score + tutor feedback |
| Adaptive recommendation | POST /generate {user_id + topics:[]} | Auto-selects unmastered topic and appropriate difficulty |
| Multi-agent synthesis V2 | POST /synthesize-v2 {count=5} | Returns 5 problems with complete agent conversation log |
| SSE real-time stream | GET /synthesize-v2/stream | Streams agent messages; final event contains statistics |
| TypeScript compilation | `npx tsc --noEmit` | Passes with zero errors |
| Backward compatibility | POST /generate + /synthesize | Legacy endpoints fully functional |

### 7.2 Performance Metrics

| Metric | V1 Pipeline | V2 Message System | Improvement |
|--------|-------------|-------------------|-------------|
| Average LLM calls per problem | 8–10 | 4–5 | ↓ 50% |
| Inter-agent communication | Shared dict (indirect) | Message bus (direct) | Qualitative leap |
| Agent autonomous decision-making | None (orchestrator-controlled) | Yes (autonomous loop) | Qualitative leap |
| Concurrent execution | Serial | asyncio concurrent | Qualitative leap |
| Frontend real-time monitoring | None | SSE real-time stream | New feature |

### 7.3 Architecture Comparison

| Feature | Pseudo Multi-Agent | True Multi-Agent (V2) |
|---------|-------------------|----------------------|
| Communication protocol | Shared dict | Structured Message |
| Communication direction | Unidirectional (Orchestrator→Agent) | Bidirectional (Agent↔Agent) |
| Workflow | Hardcoded order | Emergent collaboration |
| Agent memory | Stateless | Independent memory system |
| Tool LLM calls | Tools contain LLM calls | Tools are pure functions, zero LLM |
| Orchestration pattern | Controller | Observer |

---

## 8. Discussion

### 8.1 Design Trade-offs in the Multi-Agent System

**Message-passing vs. shared state**: The message-passing architecture (V2) provides superior traceability and loose coupling but introduces additional communication overhead. The shared-state approach (V1) is simpler to implement but difficult to scale and maintain.

**Autonomy vs. control**: The V2 agents possess genuine autonomous decision-making authority, enabling more flexible workflows but introducing the risk of deadlocks and infinite loops. These are mitigated through idle timeouts (60–180 seconds per agent) and a global timeout (600 seconds).

**LLM call efficiency**: V2 achieves approximately 50% LLM call reduction by having agents directly produce content rather than routing to another LLM-invoking tool. This is accomplished through carefully designed agent personality prompts, essentially internalizing the tool's LLM invocation logic into the agent's reasoning process.

### 8.2 Pedagogical Significance

The T2P system is not merely a technical implementation; it embodies several pedagogical principles:

1. **Zone of Proximal Development**: The adaptive difficulty algorithm ensures problems remain at an appropriate challenge level.
2. **Scaffolded Instruction**: Each problem's progressive hints guide from conceptual understanding to procedural assistance, gradually withdrawing support.
3. **Formative Assessment**: The auditing system provides actionable improvement suggestions rather than simple binary feedback.
4. **Conceptual Fusion**: The exam mode promotes integrative understanding across knowledge points rather than isolated practice.

### 8.3 Limitations

1. **LLM mathematical correctness**: Despite multiple layers of quality assurance, LLMs may still produce subtle errors in complex proofs.
2. **OCR accuracy**: Handwritten LaTeX OCR recognition accuracy is limited for illegible handwriting.
3. **Monolingual support**: Currently supports only English-language problem generation.
4. **Concurrency scale**: The actual latency reduction benefit of four-agent concurrent collaboration is constrained by LLM API rate limits.
5. **Evaluation subjectivity**: While AI auditing offers consistency advantages, score calibration lacks human-annotated benchmarks.

---

## 9. Conclusion and Future Work

### 9.1 Conclusion

This report has presented T2P — an AI-driven data synthesis system for calculus education. The system implements three core functionalities: (1) automated problem generation supporting both drill and exam modes; (2) an OCR-based intelligent auditing engine; and (3) a message-bus-based genuine multi-agent collaborative system.

T2P makes contributions to multi-agent system design: it proposes a message-driven autonomous agent architecture that achieves approximately 50% efficiency improvement and emergent agent collaboration patterns through structured communication protocols, agent personality design, and the elimination of two-layer LLM calls. The system is fully backward-compatible, with the legacy pipeline and the new message-based system coexisting and usable in parallel.

### 9.2 Future Work

1. **Mathematical verification engine integration**: Incorporate symbolic computation systems (e.g., SymPy) as independent validators to compensate for LLM deficiencies in mathematical correctness.
2. **Multimodal student modeling**: Construct finer-grained cognitive models based on student-submitted drafts and error patterns.
3. **Multilingual expansion**: Support Chinese-language mathematical problem generation and auditing.
4. **Persistent message queues**: Upgrade the MessageBus to Redis/RabbitMQ backends, supporting distributed agent deployment.
5. **Human evaluation benchmarks**: Establish human-annotated quality assessment datasets to calibrate AI audit scores.
6. **Curriculum-level planning**: Extend from single-problem generation to complete curriculum knowledge sequence planning.
7. **Dynamic agent generation**: Automatically split or merge agent roles based on task complexity.

---

## References

[1] Amini, A., et al. (2019). MathQA: Towards Interpretable Math Word Problem Solving with Operation-Based Formalisms. *NAACL-HLT*.

[2] Anthropic. (2024). The Claude Model Family.

[3] Cobbe, K., et al. (2021). Training Verifiers to Solve Math Word Problems. *arXiv:2110.14168*.

[4] Du, Y., et al. (2024). MathVC: Multi-Agent Discussion for Mathematical Reasoning Verification. *arXiv*.

[5] OpenAI. (2023). GPT-4 Technical Report.

[6] Park, J. S., et al. (2024). Generative Agents: Interactive Simulacra of Human Behavior.

[7] Qian, C., et al. (2023). ChatDev: Communicative Agents for Software Development. *ACL*.

[8] Vygotsky, L. S. (1978). Mind in Society: The Development of Higher Psychological Processes. *Harvard University Press*.

[9] Wu, Q., et al. (2023). AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. *arXiv:2308.08155*.

---

**Appendix A: System Startup Instructions**

```bash
# Backend
cd D:\数据科学理学硕士MscDS\第二学期\T2P\T2P-Final
python api_server.py

# Frontend
cd D:\数据科学理学硕士MscDS\第二学期\T2P\T2P-Final\t2p-web
npm run dev
```

**Appendix B: Key File Inventory**

See component paths detailed in Section 3, System Architecture.
