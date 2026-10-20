"""
Calculus Atelier API Server (V7.0.0)
Provides interfaces for problem generation, topic listing, intelligent auditing, user management, and adaptive recommendation.
Fix: Manual problem generation no longer overrides user-selected difficulty and mode.
"""
import os
import asyncio
import json
import logging
import time
import uuid
import re
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Path as ApiPath, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import base64

from src.batch_generator import BatchGenerator
from src.config import Config
from src.auth import AuthError, AuthIdentity
from src.auth_dependencies import (
    auth_service,
    bearer_scheme,
    current_identity,
    optional_identity,
    require_owner,
)
from src.database import (
    GenerationRunRepository,
    ProblemRepository,
    SubmissionRepository,
    get_database,
)
from src.user_session import UserSession
from src.ocr import OCRClient, OCRConfigurationError, OCRTranscriptionError
from src.grading import (
    MCQReferenceError,
    MCQSelectionError,
    assess_mcq,
    extract_selected_option,
    is_mcq_problem,
)
from src.observability import (
    configure_observability,
    current_trace_id,
    monotonic_ms,
    recorder as telemetry_recorder,
)
from src.multi_agent.coordinator import Coordinator, SynthesisConfig
from src.schemas import (
    AuditRequest,
    AuthRequest,
    GenerateRequest,
    LoginRequest,
    RecordResultRequest,
    SynthesizeRequest,
)
from src.schemas.api import USER_ID_PATTERN
from src.rag import get_retriever
from src.rag.service import digest, validate_citations
from src.learning.service import AttemptConflict, LearningService, recommend, review_schedule
from src.simulation import SIMULATION_TOPICS, SimulationInputError
from src.rag.api import router as knowledge_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_server")

app = FastAPI(
    title="Calculus Atelier API",
    version="7.0.0",
    description="Validated problem generation, tutoring, and agentic synthesis.",
)

allowed_frontend_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        (
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:3001,http://127.0.0.1:3001"
        ),
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(knowledge_router)

orchestrator = BatchGenerator()
problem_repository = ProblemRepository()
submission_repository = SubmissionRepository()
generation_run_repository = GenerationRunRepository()
observability_status = configure_observability(app, get_database().engine)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    started_ms = monotonic_ms()
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = request_id
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        trace_id = current_trace_id()
        if trace_id:
            response.headers["X-Trace-ID"] = trace_id
        return response
    finally:
        status_code = getattr(locals().get("response"), "status_code", 500)
        telemetry_recorder.record_request(
            request.method,
            request.url.path,
            status_code,
            monotonic_ms() - started_ms,
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code", "REQUEST_ERROR")
        message = detail.get("message", "Request failed")
    else:
        code = "REQUEST_ERROR"
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    fields = [
        {
            "location": list(error.get("loc", [])),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "One or more request fields are invalid.",
                "request_id": getattr(request.state, "request_id", None),
                "fields": fields,
            },
        },
    )


@app.get("/")
def read_root():
    return {
        "status": "Calculus Atelier Backend is Running",
        "dataset_version": "3.1",
        "total_problems": len(orchestrator.data_loader.problems),
        "runtime_problems": problem_repository.count(),
        "persistence": get_database().engine.dialect.name,
        "observability": observability_status.to_dict(),
    }


@app.get("/topics")
async def get_all_topics():
    try:
        topics = orchestrator.data_loader.get_main_topics()
        return {"success": True, "topics": topics}
    except Exception as e:
        logger.error(f"Failed to fetch topics: {e}")
        fallback = [
            "Limits and Continuity", "Derivatives", "Applications of Derivatives",
            "Integrals", "Applications of Integration", "Differential Equations",
            "Sequences and Series", "Parametric and Polar Curves",
            "Vector Calculus", "Multivariable Calculus", "Multiple Integrals",
            "Techniques of Integration", "Indefinite Integrals"
        ]
        return {"success": True, "topics": fallback, "note": "fallback used"}


@app.get("/capabilities")
def get_capabilities():
    return {
        "success": True,
        "grading": {
            "provider": "deepseek" if Config.AI_MODE == "live" else Config.AI_MODE,
            "model": orchestrator.llm_client.model_name,
            "input": "text",
        },
        "ai_mode": Config.AI_MODE,
        "external_calls_enabled": Config.AI_MODE == "live" and Config.ALLOW_PAID_API,
        "rag": get_retriever().status(),
        "simulation_topics": SIMULATION_TOPICS,
        "vision_ocr": ocr_client.status(),
    }


@app.get("/knowledge/sources")
def knowledge_sources():
    retriever = get_retriever()
    retriever.refresh()
    return {"success": True, "sources": retriever.sources, "retrieval": retriever.status()}


@app.get("/knowledge/chunks/{chunk_id}")
def knowledge_chunk(chunk_id: str, content_hash: str | None = None, source_version: str | None = None):
    chunk = get_retriever().get_chunk(chunk_id, content_hash)
    if chunk is None or (source_version is not None and source_version != chunk["source_version"]):
        raise HTTPException(status_code=404, detail="This source version is unavailable or withdrawn.")
    return {"success": True, "data": chunk}


def learner_problem(problem):
    """A learner response must not contain answer keys or hidden grading fixtures."""
    fields = {"id", "problem_id", "topic", "sub_topic", "problem_statement", "difficulty",
              "mode", "question_type", "options", "ai_mode", "concept_ids", "simulation_note"}
    result = {k: v for k, v in problem.items() if k in fields}
    result["scaffolding"] = [] if problem.get("mode") == "exam" else problem.get("scaffolding", [])
    return result


def public_agent_message(message):
    # Agent messages can contain entire answer keys. Only publish progress metadata.
    allowed = {"stage", "topic", "problem_id", "evidence_bundle_id", "hint_count",
               "review_kind", "note", "event", "action", "ai_mode", "run_id", "message"}
    content = message.get("content", {})
    return {**message, "content": {k: v for k, v in content.items() if k in allowed}}


# ---------- User Management ----------
def _raise_auth_error(error: AuthError):
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    ) from error


def _auth_response(token: str, identity: AuthIdentity):
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "expires_at": identity.expires_at.isoformat(),
        "user": {"user_id": identity.user_id, "role": identity.role},
    }


@app.post("/auth/register", status_code=201)
def register_user(payload: AuthRequest):
    try:
        token, identity = auth_service.register(payload.user_id, payload.password)
        UserSession(payload.user_id)
        return _auth_response(token, identity)
    except AuthError as error:
        _raise_auth_error(error)


@app.post("/auth/login")
def authenticate_user(payload: AuthRequest):
    try:
        token, identity = auth_service.login(payload.user_id, payload.password)
        return _auth_response(token, identity)
    except AuthError as error:
        _raise_auth_error(error)


@app.get("/auth/me")
def get_authenticated_user(identity: AuthIdentity = Depends(current_identity)):
    return {
        "success": True,
        "user": {"user_id": identity.user_id, "role": identity.role},
        "expires_at": identity.expires_at.isoformat(),
    }


@app.post("/auth/logout")
def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    _identity: AuthIdentity = Depends(current_identity),
):
    auth_service.logout(credentials.credentials)
    return {"success": True}


@app.post("/user/login")
def login_user(payload: LoginRequest):
    """Deprecated insecure identity-only login route."""
    raise HTTPException(
        status_code=410,
        detail={
            "code": "PASSWORD_AUTH_REQUIRED",
            "message": "Use /auth/register or /auth/login with a password.",
        },
    )


@app.get("/user/progress/{user_id}")
def get_progress(
    user_id: str = ApiPath(pattern=USER_ID_PATTERN),
    identity: AuthIdentity = Depends(current_identity),
):
    """Get detailed user progress (for dashboard use)"""
    require_owner(identity, user_id)
    session = UserSession(user_id)
    concept_evidence = LearningService().concept_summary(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "topics_status": session.progress["topics_status"],
        "total_minutes": session.progress["metadata"]["total_minutes"],
        "recommendation": recommend(session.progress, get_retriever(),
            get_capabilities()["simulation_topics"] if Config.AI_MODE == "simulation" else None, concept_evidence),
        "concept_evidence": concept_evidence,
        "review_queue": review_schedule(session.progress),
    }


@app.post("/user/record")
def record_result(
    payload: RecordResultRequest,
    identity: AuthIdentity = Depends(current_identity),
):
    """Record learning result. Fields: user_id, topic, logic_alignment_score, is_correct"""
    user_id = payload.user_id
    require_owner(identity, user_id)
    raise HTTPException(status_code=410, detail={
        "code": "SERVER_OWNED_PROGRESS",
        "message": "Progress is saved automatically from /audit. Client-supplied scores are no longer accepted.",
    })


# ---------- Problem Generation (with Adaptive Recommendation) ----------
@app.post("/generate")
async def generate_questions(
    req: GenerateRequest,
    identity: AuthIdentity | None = Depends(optional_identity),
):
    """
    Generate questions, supports adaptive recommendation mode.
    If user_id is provided and topics are not specified (i.e., 'Continue Learning' mode),
    the system automatically selects topic, difficulty, and mode based on user proficiency.
    Difficulty and mode are preserved during manual selection.
    """
    started_at = time.perf_counter()
    request_topics = list(req.topics)
    request_difficulty = req.difficulty
    request_mode = req.mode
    try:
        if req.user_id:
            if identity is None:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
                )
            require_owner(identity, req.user_id)

        # --- Adaptive Recommendation Logic ---
        if req.user_id:
            user_session = UserSession(req.user_id)
            recommended = recommend(user_session.progress, get_retriever(),
                get_capabilities()["simulation_topics"] if Config.AI_MODE == "simulation" else None,
                LearningService().concept_summary(req.user_id)) or user_session.get_current_task_params()
            # If front-end does not pass any topics, user clicked 'Continue Learning', use recommendations
            if not request_topics:
                request_topics = [recommended["topic"]]
                request_difficulty = recommended["difficulty"]
                request_mode = recommended["mode"]
                logger.info(f"Adaptive Recommendation: User {req.user_id} -> Topic: {recommended['topic']}, Difficulty: {recommended['difficulty']}, Mode: {recommended['mode']}")
            # If front-end specifically selected topics, preserve manual difficulty and mode settings
            else:
                logger.info(f"Manual Generation: User {req.user_id} selected Topic {request_topics}, Difficulty {request_difficulty}, Mode {request_mode}; bypassing recommendation override")

        if not request_topics:
            raise HTTPException(
                status_code=400,
                detail={"code": "TOPIC_REQUIRED", "message": "Select at least one topic."},
            )

        available_topics = set(orchestrator.data_loader.get_main_topics())
        unknown_topics = [topic for topic in request_topics if topic not in available_topics]
        if unknown_topics:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "UNKNOWN_TOPIC",
                    "message": f"Unknown topic(s): {', '.join(unknown_topics)}",
                },
            )

        if Config.AI_MODE == "simulation":
            supported = get_capabilities()["simulation_topics"]
            if any(topic not in supported for topic in request_topics):
                raise HTTPException(status_code=422, detail={"code": "SIMULATION_TOPIC_UNAVAILABLE",
                    "message": "Offline fixtures currently cover: " + ", ".join(supported)})

        # Call generator
        # LLM generation is synchronous and can take minutes. Running it on the
        # event loop made lightweight routes such as /topics and /auth time out.
        problems = await asyncio.to_thread(
            orchestrator.generator.generate_batch,
            topics=request_topics,
            num=req.num,
            mode=request_mode,
            difficulty=request_difficulty,
            question_type=req.question_type.value,
        )
        if not problems:
            raise HTTPException(status_code=500, detail="Generation failed, please try again later")

        output_dir = Path(orchestrator.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for prob in problems:
            existing_id = str(prob.get('problem_id') or prob.get('id') or '')
            new_id = existing_id if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", existing_id) and existing_id != 'T2P_GEN_1' else uuid.uuid4().hex[:12]
            prob['id'] = prob['problem_id'] = new_id

            file_path = output_dir / f"{new_id}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(prob, f, ensure_ascii=False, indent=2)
            problem_repository.upsert(prob, source="single_agent")

        generation_run_repository.create(
            pipeline="single_agent",
            topics=request_topics,
            target_count=req.num,
            generated_count=len(problems),
            status="completed",
            mode=request_mode,
            question_type=req.question_type.value,
            difficulty=request_difficulty,
            user_id=req.user_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            model=orchestrator.llm_client.model_name,
        )
        telemetry_recorder.record_generation(
            "single_agent",
            "completed",
            (time.perf_counter() - started_at) * 1000,
        )

        return {"success": True, "ai_mode": Config.AI_MODE,
                "data": [learner_problem(p) for p in problems]}

    except HTTPException:
        raise
    except Exception:
        logger.exception("Problem generation exception")
        generation_run_repository.create(
            pipeline="single_agent",
            topics=request_topics,
            target_count=req.num,
            generated_count=0,
            status="failed",
            mode=request_mode,
            question_type=req.question_type.value,
            difficulty=request_difficulty,
            user_id=req.user_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            model=Config.LLM_MODEL,
            error_code="GENERATION_FAILED",
        )
        telemetry_recorder.record_generation(
            "single_agent",
            "failed",
            (time.perf_counter() - started_at) * 1000,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "GENERATION_FAILED",
                "message": "Problem generation failed. Please try again later.",
            },
        )


# ---------- Intelligent Audit ----------
ocr_client = OCRClient()


@app.post("/audit")
async def audit_submission(
    req: AuditRequest,
    identity: AuthIdentity | None = Depends(optional_identity),
):
    try:
        if req.user_id:
            if identity is None:
                raise HTTPException(
                    status_code=401,
                    detail={"code": "AUTH_REQUIRED", "message": "Authentication is required."},
                )
            require_owner(identity, req.user_id)
        request_hash = digest(req.model_dump(exclude={"attempt_id"}))
        learning_service = LearningService()
        if req.attempt_id:
            saved = learning_service.lookup(req.user_id or "anonymous", req.attempt_id, request_hash)
            if saved:
                return saved
        raw_input = req.text_answer or req.student_work_image
        image_bytes = None
        image_mime_type = "image/jpeg"
        text_answer = None
        is_mcq_input = False
        ocr_text = None

        # 1. Determine if input is an image or plain text option
        if raw_input and "," in raw_input and "base64" in raw_input:
            # --- Image Mode: parse image, then run OCR ---
            try:
                header, base64_str = raw_input.split(",", 1)
                image_mime_type = header.removeprefix("data:").split(";", 1)[0]
                if image_mime_type not in {"image/jpeg", "image/png", "image/webp"}:
                    raise HTTPException(
                        status_code=415,
                        detail={
                            "code": "UNSUPPORTED_IMAGE_TYPE",
                            "message": "Use a JPEG, PNG, or WebP image.",
                        },
                    )
                image_bytes = base64.b64decode(base64_str.strip(), validate=True)
                if len(image_bytes) > 5_000_000:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "IMAGE_TOO_LARGE",
                            "message": "Images must be 5 MB or smaller.",
                        },
                    )
                logger.info("Image input detected, running dedicated vision OCR...")
                ocr_text = await asyncio.to_thread(
                    ocr_client.transcribe,
                    image_bytes,
                    image_mime_type,
                )
                text_answer = ocr_text
                image_bytes = None  # DeepSeek receives only the OCR transcript.
                logger.info("Vision OCR succeeded; sending transcript to DeepSeek grading.")
            except HTTPException:
                raise
            except OCRConfigurationError as error:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "VISION_OCR_NOT_CONFIGURED",
                        "message": str(error),
                    },
                ) from error
            except OCRTranscriptionError as error:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "code": "VISION_OCR_FAILED",
                        "message": str(error),
                    },
                ) from error
            except (ValueError, base64.binascii.Error) as error:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "INVALID_IMAGE_DATA",
                        "message": "The uploaded image data is invalid.",
                    },
                ) from error
        else:
            # --- Text Mode: legacy MCQ selection or manually typed answer ---
            text_answer = raw_input
            if text_answer:
                logger.info("Text input detected; performing text audit.")

        # 2. Find problem data
        problem = problem_repository.get(req.problem_id)
        if not problem:
            problem = orchestrator.data_loader.find_problem_by_id(
                problem_id=req.problem_id,
                output_dir=orchestrator.output_dir
            )
        if not problem:
            raise HTTPException(status_code=404, detail=f"Problem ID '{req.problem_id}' not found")
        # Exam protection is derived from stored state, not a learner-controlled switch.
        req.is_exam_mode = bool(req.is_exam_mode or problem.get("mode") == "exam")

        # Objective correctness is decided by exact option-key comparison. The
        # LLM receives the result and full option content only to explain it.
        mcq_assessment = None
        if is_mcq_problem(problem):
            selected_option = extract_selected_option(
                req.selected_option,
                text_answer,
            )
            if not selected_option:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "OPTION_REQUIRED",
                        "message": "Select one of the available options.",
                    },
                )
            try:
                mcq_assessment = assess_mcq(problem, selected_option)
            except MCQSelectionError as error:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "INVALID_OPTION_SELECTION",
                        "message": str(error),
                    },
                ) from error
            except MCQReferenceError as error:
                logger.error("Invalid MCQ reference for %s: %s", req.problem_id, error)
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "INVALID_REFERENCE_ANSWER",
                        "message": "This question cannot be graded until its reference answer is corrected.",
                    },
                ) from error

            is_mcq_input = True
            text_answer = (
                f"Selected option {mcq_assessment.selected_key}: "
                f"{mcq_assessment.selected_content}"
            )
        elif req.selected_option:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "OPTION_NOT_APPLICABLE",
                    "message": "The current problem is not a multiple-choice question.",
                },
            )

        evidence = await asyncio.to_thread(
            get_retriever().retrieve,
            " ".join([str(problem.get("topic", "")), " ".join(problem.get("concept_ids", [])),
                      str(problem.get("problem_statement", ""))]),
            topics=[str(problem.get("topic", ""))], purpose="tutor", exam=req.is_exam_mode,
            required_concepts=problem.get("concept_ids", []),
        )

        # 3. Call Tutor module
        review_json = {}
        try:
            raw_review = await asyncio.to_thread(
                orchestrator.llm_client.mentor_review,
                student_work_image=None,
                student_text_answer=text_answer,
                problem_data=problem,
                is_exam_mode=req.is_exam_mode,
                mcq_assessment=(
                    mcq_assessment.to_dict() if mcq_assessment else None
                ),
                evidence_bundle=evidence,
            )

            # 4. Parse results
            cleaned = raw_review.strip().replace("```json", "").replace("```", "").strip()
            review_json = json.loads(cleaned)
            if not isinstance(review_json, dict):
                raise ValueError("Tutor review must be a JSON object.")
        except Exception as error:
            if mcq_assessment is None:
                raise
            # Exact MCQ grading remains available if the explanatory model is
            # temporarily unavailable or returns malformed JSON.
            logger.exception(
                "AI mentor feedback failed for MCQ %s; using deterministic feedback: %s",
                req.problem_id,
                error,
            )
            review_json = {}

        if mcq_assessment and review_json:
            ai_verdict = review_json.get("is_correct")
            if (
                not isinstance(ai_verdict, bool)
                or ai_verdict != mcq_assessment.is_correct
            ):
                logger.warning(
                    "Discarding contradictory AI feedback for MCQ %s "
                    "(AI=%r, deterministic=%s).",
                    req.problem_id,
                    ai_verdict,
                    mcq_assessment.is_correct,
                )
                review_json = {}

        # 5. Precise score calibration logic
        is_correct = bool(review_json.get("is_correct", False))
        try:
            raw_score = float(review_json.get("logic_alignment_score", 0))
        except (TypeError, ValueError):
            raw_score = 0

        if mcq_assessment:
            # Never allow a probabilistic model response to override an exact
            # comparison between the submitted key and the stored answer key.
            is_correct = mcq_assessment.is_correct
            final_score = 100 if is_correct else 0
        elif is_mcq_input:
            if is_correct:
                final_score = 100
            else:
                final_score = min(raw_score, 30) if raw_score > 30 else raw_score
        else:
            # Image/OCR: maintain AI scoring with a baseline
            if is_correct and raw_score < 60:
                final_score = 80
            else:
                final_score = raw_score

        if mcq_assessment and is_correct:
            fallback_error = "Option correct."
            fallback_feedback = (
                f"Your selection {mcq_assessment.selected_key} matches the "
                "verified reference option."
            )
            fallback_hint = "Review the reference reasoning, then continue to the next problem."
        elif mcq_assessment:
            fallback_error = "The selected option does not match the reference answer."
            fallback_feedback = "Recheck the mathematical condition used to distinguish the options."
            fallback_hint = (
                "Review the relevant definition and eliminate options one condition at a time."
                if req.is_exam_mode
                else f"Compare your choice with the reasoning in the reference solution for "
                f"option {mcq_assessment.answer_key}."
            )
        else:
            fallback_error = "Analysis complete"
            fallback_feedback = ""
            fallback_hint = ""

        grounding = validate_citations(review_json, evidence, exam=req.is_exam_mode)
        error_analysis = review_json.get("error_analysis") or fallback_error
        tutor_feedback = review_json.get("tutor_feedback") or fallback_feedback
        next_hint = review_json.get("next_hint") or fallback_hint
        if req.user_id:
            UserSession(req.user_id)
        response = {
            "success": True,
            "is_correct": is_correct,
            "logic_alignment_score": max(0, min(100, final_score)),
            "error_analysis": error_analysis,
            "tutor_feedback": tutor_feedback,
            "next_hint": next_hint,
            "ocr_text": ocr_text or text_answer or "",
            "ai_mode": Config.AI_MODE,
            **grounding,
        }
        return learning_service.save(
            user_id=req.user_id, request_key=req.attempt_id, request_hash=request_hash,
            problem=problem, response=response, evidence=evidence, text_answer=text_answer,
        )

    except AttemptConflict as error:
        raise HTTPException(status_code=409, detail={"code": "ATTEMPT_CONFLICT", "message": str(error)}) from error
    except SimulationInputError as error:
        raise HTTPException(status_code=422, detail={"code": "SIMULATION_INPUT_REQUIRED", "message": str(error)}) from error
    except HTTPException:
        raise
    except Exception:
        logger.exception("Audit exception")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "AUDIT_FAILED",
                "message": "The audit service could not complete this submission.",
            },
        )


@app.post("/synthesize")
async def multi_agent_synthesize(req: SynthesizeRequest):
    """
    Multi-agent synthesis with autonomous agent collaboration.

    4 agents (Synthesizer, Scaffolder, Reviewer, Curator) communicate
    via structured messages through a MessageBus, run concurrently,
    and autonomously decide who to collaborate with — the workflow
    emerges from agent interactions, not a hardcoded pipeline.
    """
    try:
        config = SynthesisConfig(
            topics=req.topics,
            target_count=req.count,
            mode=req.mode,
            difficulty=req.difficulty,
            question_type=req.question_type.value,
            timeout_seconds=600.0,
        )
        coordinator = Coordinator(config)
        result = await coordinator.synthesize()
        for problem in result.problems:
            problem_repository.upsert(problem, source="multi_agent")
        generation_run_repository.create(
            pipeline="multi_agent",
            topics=req.topics,
            target_count=req.count,
            generated_count=result.total_problems,
            status="completed" if result.success else "partial",
            mode=req.mode,
            question_type=req.question_type.value,
            difficulty=req.difficulty,
            duration_ms=int(result.duration_seconds * 1000),
            model=Config.LLM_MODEL,
            error_code=result.error or None,
        )
        telemetry_recorder.record_generation(
            "multi_agent",
            "completed" if result.success else "partial",
            result.duration_seconds * 1000,
        )

        return {
            "success": result.success,
            "total_problems": result.total_problems,
            "statistics": result.statistics,
            "problems": [learner_problem(p) for p in result.problems],
            "total_llm_calls": result.total_llm_calls,
            "total_agent_messages": result.total_agent_messages,
            "duration_seconds": result.duration_seconds,
            "terminated_by": result.terminated_by,
            "conversation_log": [public_agent_message(m) for m in result.conversation_log],
            "ai_mode": Config.AI_MODE,
            "error": result.error,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Multi-Agent synthesis failed")
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNTHESIS_FAILED",
                "message": "Multi-agent synthesis failed.",
            },
        )


@app.get("/synthesize/stream")
async def stream_synthesis(
    topics: str = Query(..., description="Comma-separated topic list"),
    count: int = Query(5, ge=1, le=20, description="Number of problems to generate"),
    mode: str = Query("drill", pattern="^(drill|exam)$", description="Mode: drill or exam"),
    difficulty: int = Query(3, ge=1, le=5, description="Difficulty level 1-5"),
    question_type: str = Query("calculation", pattern="^(calculation|mcq|fill_in)$", description="Type: calculation, mcq, or fill_in"),
):
    """
    Stream multi-agent synthesis progress via Server-Sent Events.

    The frontend can connect to this endpoint to watch agent
    conversations in real-time as problems are generated.
    """
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]

    async def event_generator():
        config = SynthesisConfig(
            topics=topic_list,
            target_count=count,
            mode=mode,
            difficulty=difficulty,
            question_type=question_type,
        )
        coordinator = Coordinator(config)

        # Start synthesis in background task
        task = asyncio.create_task(coordinator.synthesize())

        last_msg_index = 0
        heartbeat_counter = 0
        while not task.done():
            # Stream new messages as SSE
            new_msgs = coordinator.message_bus.get_all_messages_since(last_msg_index)
            for msg in new_msgs:
                yield f"data: {json.dumps(public_agent_message(msg.to_dict()), ensure_ascii=False)}\n\n"
                heartbeat_counter = 0  # Reset heartbeat when we have activity
            last_msg_index += len(new_msgs)

            # Send heartbeat comment every 15s to keep SSE alive during LLM calls
            heartbeat_counter += 1
            if heartbeat_counter >= 15:
                yield ": heartbeat\n\n"
                heartbeat_counter = 0

            await asyncio.sleep(1)

        # Send remaining messages
        new_msgs = coordinator.message_bus.get_all_messages_since(last_msg_index)
        for msg in new_msgs:
            yield f"data: {json.dumps(public_agent_message(msg.to_dict()), ensure_ascii=False)}\n\n"

        # Send completion event
        result = await task
        for problem in result.problems:
            problem_repository.upsert(problem, source="multi_agent")
        generation_run_repository.create(
            pipeline="multi_agent",
            topics=topic_list,
            target_count=count,
            generated_count=result.total_problems,
            status="completed" if result.success else "partial",
            mode=mode,
            question_type=question_type,
            difficulty=difficulty,
            duration_ms=int(result.duration_seconds * 1000),
            model=Config.LLM_MODEL,
            error_code=result.error or None,
        )
        telemetry_recorder.record_generation(
            "multi_agent",
            "completed" if result.success else "partial",
            result.duration_seconds * 1000,
        )
        completion_data = {
            "event": "complete",
            "success": result.success,
            "total_problems": result.total_problems,
            "problems": [learner_problem(p) for p in result.problems],
            "ai_mode": Config.AI_MODE,
            "statistics": result.statistics,
            "total_llm_calls": result.total_llm_calls,
            "total_agent_messages": result.total_agent_messages,
            "duration_seconds": result.duration_seconds,
            "terminated_by": result.terminated_by,
        }
        yield f"data: {json.dumps(completion_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
