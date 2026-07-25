"""
T2P API Server (V5.0.1)
Provides interfaces for problem generation, topic listing, intelligent auditing, user management, and adaptive recommendation.
Fix: Manual problem generation no longer overrides user-selected difficulty and mode.
"""
# Force Hugging Face domain to point to the domestic mirror site
import os
# Use port 6987 as seen in the screenshot
os.environ['http_proxy'] = 'http://127.0.0.1:6987'
os.environ['https_proxy'] = 'http://127.0.0.1:6987'
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import base64
import json
import logging
import uuid
from pathlib import Path

from src.batch_generator import BatchGenerator
from src.config import Config
from src.user_session import UserSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_server")

app = FastAPI(title="T2P API Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = BatchGenerator()


# ---------- Request/Response Models ----------
class GenerateRequest(BaseModel):
    topics: List[str] = []
    num: int = 1
    mode: str = "drill"
    difficulty: int = 3
    question_type: str = "calculation"
    user_id: Optional[str] = None          # Used for adaptive recommendation


class AuditRequest(BaseModel):
    problem_id: str
    student_work_image: str
    is_exam_mode: bool = False


@app.get("/")
def read_root():
    return {
        "status": "T2P Backend is Running",
        "dataset_version": "3.1",
        "total_problems": len(orchestrator.data_loader.problems)
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


# ---------- User Management ----------
@app.post("/user/login")
def login_user(payload: dict):
    """User login or creation. Field: user_id"""
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    session = UserSession(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "total_topics": len(session.roadmap),
        "progress": session.progress["topics_status"]
    }


@app.get("/user/progress/{user_id}")
def get_progress(user_id: str):
    """Get detailed user progress (for dashboard use)"""
    session = UserSession(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "topics_status": session.progress["topics_status"],
        "total_minutes": session.progress["metadata"]["total_minutes"]
    }


@app.post("/user/record")
def record_result(payload: dict):
    """Record learning result. Fields: user_id, topic, logic_alignment_score, is_correct"""
    user_id = payload.get("user_id")
    topic = payload.get("topic")
    logic_score = payload.get("logic_alignment_score", 0)
    is_passed = payload.get("is_correct", False)

    if not user_id or not topic:
        raise HTTPException(status_code=400, detail="user_id and topic required")

    session = UserSession(user_id)
    try:
        session.record_result(topic, logic_score, is_passed)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Problem Generation (with Adaptive Recommendation) ----------
@app.post("/generate")
async def generate_questions(req: GenerateRequest):
    """
    Generate questions, supports adaptive recommendation mode.
    If user_id is provided and topics are not specified (i.e., 'Continue Learning' mode),
    the system automatically selects topic, difficulty, and mode based on user proficiency.
    Difficulty and mode are preserved during manual selection.
    """
    try:
        # --- Adaptive Recommendation Logic ---
        if req.user_id:
            user_session = UserSession(req.user_id)
            recommended = user_session.get_current_task_params()
            # If front-end does not pass any topics, user clicked 'Continue Learning', use recommendations
            if not req.topics:
                req.topics = [recommended["topic"]]
                req.difficulty = recommended["difficulty"]
                req.mode = recommended["mode"]
                logger.info(f"Adaptive Recommendation: User {req.user_id} -> Topic: {recommended['topic']}, Difficulty: {recommended['difficulty']}, Mode: {recommended['mode']}")
            # If front-end specifically selected topics, preserve manual difficulty and mode settings
            else:
                logger.info(f"Manual Generation: User {req.user_id} selected Topic {req.topics}, Difficulty {req.difficulty}, Mode {req.mode}; bypassing recommendation override")

        # Call generator
        problems = orchestrator.generator.generate_batch(
            topics=req.topics,
            num=req.num,
            mode=req.mode,
            difficulty=req.difficulty,
            question_type=req.question_type
        )
        if not problems:
            raise HTTPException(status_code=500, detail="Generation failed, please try again later")

        output_dir = Path(orchestrator.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for prob in problems:
            existing_id = prob.get('id', '')
            if not existing_id or existing_id == 'T2P_GEN_1':
                new_id = str(uuid.uuid4())[:8]
                prob['id'] = new_id
            else:
                new_id = existing_id
            prob['problem_id'] = prob.get('problem_id') or new_id

            file_path = output_dir / f"{new_id}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(prob, f, ensure_ascii=False, indent=2)

        return {"success": True, "data": problems}

    except Exception as e:
        logger.error(f"Problem generation exception: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Intelligent Audit ----------
@app.post("/audit")
async def audit_submission(req: AuditRequest):
    try:
        raw_input = req.student_work_image
        image_bytes = None
        text_answer = None

        # 1. Determine if input is an image or plain text option
        if raw_input and "," in raw_input and "base64" in raw_input:
            # Base64 Image
            try:
                base64_str = raw_input.split(",")[1]
                image_bytes = base64.b64decode(base64_str.strip())
                logger.info("Image input detected, performing multimodal audit...")
            except Exception as e:
                logger.error(f"Image parsing failed: {e}")
                text_answer = raw_input # Fallback to text if parsing fails
        else:
            # Multiple choice option or manually typed text
            text_answer = raw_input
            logger.info(f"Text input detected: {text_answer}, performing text audit...")

        # 2. Find problem data
        problem = orchestrator.data_loader.find_problem_by_id(
            problem_id=req.problem_id,
            output_dir=orchestrator.output_dir
        )
        if not problem:
            raise HTTPException(status_code=404, detail=f"Problem ID '{req.problem_id}' not found")

        # 3. Call Tutor module
        raw_review = orchestrator.gemini_client.mentor_review(
            student_work_image=image_bytes,
            student_text_answer=text_answer,
            problem_data=problem,
            is_exam_mode=req.is_exam_mode
        )

        # 4. Parse results
        try:
            cleaned = raw_review.strip().replace("```json", "").replace("```", "").strip()
            review_json = json.loads(cleaned)
        except Exception as e:
            logger.error(f"JSON parsing failed: {e}")
            review_json = {}

        # 5. Precise score calibration logic
        is_correct = review_json.get("is_correct", False)
        raw_score = review_json.get("logic_alignment_score", 0)

        # --- Logic alignment score calibration for multiple choice ---
        if text_answer:  # If directly clicking an option
            if is_correct:
                final_score = 100  # Correct selection must be 100 points
            else:
                # Incorrect selection should yield a low score; override AI if it provides a high score
                final_score = min(raw_score, 30) if raw_score > 30 else raw_score
        else:
            # For handwritten image uploads, maintain AI scoring with a baseline
            if is_correct and raw_score < 60:
                final_score = 80  # Ensure passing score if correct
            else:
                final_score = raw_score

        return {
            "success": True,
            "is_correct": is_correct,
            "logic_alignment_score": final_score,
            "error_analysis": review_json.get("error_analysis", "Analysis complete"),
            "tutor_feedback": review_json.get("tutor_feedback", ""),
            "next_hint": review_json.get("next_hint", ""),
            "ocr_text": text_answer if text_answer else "Extracted from image"
        }

    except Exception as e:
        logger.error(f"Audit exception: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")