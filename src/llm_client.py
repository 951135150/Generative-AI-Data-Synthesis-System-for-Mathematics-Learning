"""
LLM Client - DeepSeek V4 Pro (OpenAI-compatible)
Supports text generation, multimodal vision audit, and 429 auto-retry.
"""
import logging
import time
import base64
import json
from typing import Optional, Dict
from openai import OpenAI
from src.config import Config

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM Client powered by DeepSeek V4 Pro (OpenAI-compatible API)"""

    def __init__(self):
        self.model_name = Config.LLM_MODEL
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = Config.DEEPSEEK_BASE_URL

        if not self.api_key:
            msg = "DEEPSEEK_API_KEY not found in environment variables"
            logger.error(msg)
            raise ValueError(msg)

        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            logger.info(f"DeepSeek client initialized (Model: {self.model_name}, Base: {self.base_url})")
        except Exception as e:
            logger.error(f"Client initialization failed: {str(e)}")
            raise

    def generate(self, prompt: str, image_bytes: Optional[bytes] = None,
                 mime_type: str = "image/jpeg",
                 response_mime_type: str = None,
                 temperature: float = 0.5) -> Optional[str]:
        """
        Core generation method.
        Supports text-only and multimodal (image + text) input with high-availability retry logic.
        """
        task_label = "Visual Audit" if image_bytes else "Text generation/audit"

        messages = []

        if image_bytes and isinstance(image_bytes, bytes):
            b64 = base64.b64encode(image_bytes).decode('utf-8')
            data_url = f"data:{mime_type};base64,{b64}"
            messages.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt}
                ]
            })
        else:
            messages.append({"role": "user", "content": prompt})

        extra_kwargs = {}
        if response_mime_type:
            extra_kwargs["response_format"] = {"type": response_mime_type}

        for attempt in range(3):
            try:
                logger.info(f"{task_label} | Request sent (Attempt {attempt + 1}/3)...")

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=Config.DEFAULT_MAX_TOKENS,
                    top_p=Config.DEFAULT_TOP_P,
                    **extra_kwargs
                )

                if response and response.choices:
                    content = response.choices[0].message.content
                    if content:
                        return content

                if response.choices and response.choices[0].finish_reason == "content_filter":
                    logger.error("Response intercepted by content safety policy.")
                    return None

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "rate" in err_msg.lower():
                    if attempt < 2:
                        wait_time = 90
                        logger.warning(f"Node is busy (429). Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                if attempt < 2:
                    logger.warning(f"Temporary error: {err_msg}. Retrying in 5s...")
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"Task ultimately failed: {err_msg}")
                    raise e
        return None

    def mentor_review(self, student_work_image: Optional[bytes] = None,
                      problem_data: Dict = {},
                      is_exam_mode: bool = False,
                      student_text_answer: Optional[str] = None,
                      mcq_assessment: Optional[Dict] = None) -> str:
        """
        Encapsulated mentor audit interface: supports images, plain text, or a combination of both.

        Args:
            student_work_image: bytes (Binary data of photos)
            problem_data: Topic metadata
            is_exam_mode: Mode switch
            student_text_answer: Multiple choice question options or text answers entered by students
            mcq_assessment: Deterministic option-key comparison supplied by the backend
        """
        scaffolding_info = (
            "Not available (exam mode prohibited prompt)"
            if is_exam_mode
            else problem_data.get('scaffolding')
        )

        input_descriptions = []
        if student_work_image:
            input_descriptions.append("Handwritten answer photo")
        if student_text_answer:
            input_descriptions.append(f"Text answer content (submitted: {student_text_answer})")

        input_type_desc = " + ".join(input_descriptions) if input_descriptions else "No content submitted"
        option_map = problem_data.get("options")
        option_map_text = (
            json.dumps(option_map, ensure_ascii=False, indent=2)
            if isinstance(option_map, dict)
            else "Not applicable"
        )
        mcq_assessment_text = (
            json.dumps(mcq_assessment, ensure_ascii=False, indent=2)
            if mcq_assessment
            else "Not applicable"
        )

        mode_instruction = (
            "[Mode: Strict Exam]\n- It is strictly prohibited to provide specific solutions.\n- Emphasize the logical discontinuity."
            if is_exam_mode else
            "[Mode: Inspirational Practice]\n- Use Socratic method to guide students to discover errors."
        )

        prompt = f"""
You are a professional calculus instructor. Please audit the student's submitted work.
The student wrote their solution by hand (natural mathematical handwriting), NOT in LaTeX.
Submission Type: {input_type_desc}

{mode_instruction}

【Reference Benchmark】
- Problem Statement: {problem_data.get('problem_statement')}
- Available Options (key -> full content):
{option_map_text}
- Stored Reference Answer Key: {problem_data.get('answer') or "Not applicable"}
- Reference Solution: {problem_data.get('solution')}

【Student's Submitted Work】
{student_text_answer if student_text_answer else "(See the handwritten work in the image — the student wrote natural math, not LaTeX code)"}

【Deterministic MCQ Assessment】
{mcq_assessment_text}

【Audit and Scoring Criteria - Extremely Important】
1. **Multiple Choice Question Special Logic**:
 - The backend has already compared the submitted option key and content with the stored reference
   answer. When "Deterministic MCQ Assessment" is present, its `is_correct` value is authoritative.
   Your JSON `is_correct` MUST match it; do not attempt to replace the deterministic verdict.
 - Use the complete option map, selected option content, reference option content, and solution to
   explain why the selection is correct or incorrect.
 - A correct option receives a logic score of 100. An incorrect option receives a logic score of 0.
 - When the options are correct, the 'tutor_feedback' should focus on affirming the conclusion and
   briefly summarizing the mathematical principles behind the option, rather than criticizing the lack
   of process.
 - In strict exam mode, do not reveal the correct option or full solution after an incorrect selection.
2. **Calculation/deduction question logic**:
   If students submit handwritten photos or long text
   1. **Problem Consistency Check (CRITICAL)**:
   - First, compare the problem in the student's submission (image or text) with the "Reference Benchmark".
   - If the student is solving a COMPLETELY DIFFERENT problem (e.g., different functions or goals), you
     MUST set "is_correct": false and "logic_alignment_score": 0.
   - In the "error_analysis", state: "The submitted work does not match the current problem."
   - If the answer is wrong or from another problem, do NOT provide encouraging feedback that validates
     their wrong steps.
   2.deductions, perform logical alignment audit as is, including: error diagnosis: locating the wrong
   location (calculation, concept, or formula), integrity check: checking for missing key proof steps.
3. **Error diagnosis**: If the option is incorrect, please use Socratic guidance to ask students if they
   have ignored a variable when applying relevant formulas (such as cosine theorem or derivative chain rule).

【output format (JSON ONLY)】
{{
    "is_correct": bool,
    "logic_alignment_score": int,
    "error_analysis": "If it is a multiple-choice question and correct, please write 'option correct'; If wrong, analyze possible cognitive biases",
    "tutor_feedback": "Encouragement feedback, if the correct option, briefly describe its logic (LaTeX)",
    "next_hint": "Guide the next step of thinking"
}}
"""

        return self.generate(
            prompt=prompt,
            image_bytes=student_work_image,
            temperature=0.3
        )
