"""
Gemini Client - Mentor Audit Enhanced Version (supports visual correction, text simulation, and 429 automatic avoidance)
"""
import logging
import time
import os
import sys
import json
from typing import Optional, Union, List, Dict
# 1. Get the standard package path of venv under the current project
#Note: We use relative paths here to ensure that it can automatically find the venv under your current project
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_site_packages = os.path.join(current_dir, "venv", "Lib", "site-packages")

# 2. Insert this path into the first position of the search list
if os.path.exists(venv_site_packages):
    sys.path.insert(0, venv_site_packages)
    print(f"--- Forcefully mounted virtual environment package path: {venv_site_packages} ---")
else:
    print("--- Warning: Venv path not found, please check if the Venv folder exists ---")

# 3. The current import will prioritize searching from Venv
from src.config import Config
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        """Initialize Gemini client - Force adaptation to Vertex AI"""
        # 1. Retrieve Vertex AI specific parameters from the Config class
        self.target_project = Config.PROJECT_ID
        self.target_location = Config.LOCATION
        self.model_name = Config.GEMINI_MODEL
        # API_KEY is usually not required in Vertex mode, but references are kept as a precautionary measure
        self.api_key = Config.API_KEY

        try:
            # 2. Core logic: Prioritize/enforce the use of Vertex AI mode
            # If Config. API_KEY is empty or you want to force the use of GCP credentials, make sure vertexai=True
            if not self.api_key:
                logger.info(f"Initializing Vertex AI client (Project: {self.target_project})...")
                self.client = genai.Client(
                    vertexai=True,
                    project=self.target_project,
                    location=self.target_location
                )
            else:
                # Compatibility mode: If API_KEY is provided, follow the AI Studio path
                logger.info("Detected API_KEY, using API key authentication mode...")
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options={'api_version': 'v1alpha'}
                )


            logger.info(f"Node/Region: {self.target_location}")
            logger.info(f"GCP project: {self.target_project}")
            logger.info(f"Core model: {self.model_name}")


        except Exception as e:
            logger.error(f"Gemini client initialization failed, please check GCP credentials or project ID: {str(e)}")
            raise

    def generate(self, prompt: str, image_bytes: Optional[bytes] = None,
                 mime_type: str = "image/jpeg",
                 response_mime_type: str = "application/json",
                 temperature: float = 0.5) -> Optional[str]:
        """
        Core generation method: Supports multimodal input and high availability retry logic
        """
        contents = []

        # Only add image parts when image_bytes is binary and not empty
        if image_bytes and isinstance(image_bytes, bytes):
            contents.append(
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            )

        contents.append(prompt)

        generate_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=16384,
            top_p=0.95,
            response_mime_type=response_mime_type
        )

        for attempt in range(3):
            try:
                task_label = "Visual Audit" if image_bytes else "Text auditing/generation"
                logger.info(f"{task_label} |Request is being sent (The No. {attempt + 1}/3 attempt)...")

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generate_config
                )

                if response and response.text:
                    return response.text

                if response.candidates and response.candidates[0].finish_reason == "SAFETY":
                    logger.error("Response intercepted by security policy。")
                    return None

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < 2:
                        wait_time = 90
                        logger.warning(f"The node is busy (429). wait quietly {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                if attempt < 2:
                    logger.warning(f"Temporary error: {err_msg}。Try again in 5 seconds ..")
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"The task ultimately failed: {err_msg}")
                    raise e
        return None

    def mentor_review(self, student_work_image: Optional[bytes] = None,
                      problem_data: Dict = {},
                      is_exam_mode: bool = False,
                      student_text_answer: Optional[str] = None) -> str:
        """
        Encapsulated mentor audit interface: supports images, plain text, or a combination of both

        Args:
            student_work_image: bytes (Binary data of photos)
            problem_data: Topic metadata
            is_exam_mode: Mode switch
            student_text_answer: Multiple choice question options or text answers entered by students
        """
        scaffolding_info = "Not available (exam mode prohibited prompt)" if is_exam_mode else problem_data.get('scaffolding')

        # --- 智能负载构建 ---
        input_descriptions = []
        if student_work_image:
            input_descriptions.append("Handwritten answer photo")
        if student_text_answer:
            input_descriptions.append(f"Text answer content (submitted content: {student_text_answer})")

        input_type_desc = " + ".join(input_descriptions) if input_descriptions else "No content submitted"

        mode_instruction = (
            "[Mode: Strict Exam] \ n- It is strictly prohibited to provide specific solutions.\Emphasize the logical discontinuity。"
            if is_exam_mode else
            "[Mode: Inspirational Practice] \ n- Use Socratic method to guide students to discover errors."
        )

        # Construct the final Prompt to be sent to AI
        # --- src/gemini_client.py ---

        prompt = f"""
                You are a professional calculus instructor. Please audit the submitted content of the students.
                Submission Type: {input_type_desc}

                {mode_instruction}

                【Reference Benchmark】
                - Title Description: {problem_data.get('problem_statement')}
                - Standard answers/options: {problem_data.get('solution')} 

                【Specific content submitted by students】
                {student_text_answer if student_text_answer else "(See image content)"}

                【Audit and Scoring Criteria - Extremely Important】
                1. **Multiple Choice Question Special Logic**: If the content submitted by the student is a clear option 
                (such as A, B, C, D)：
                 - If the option matches the standard answer, it should be judged as correct（is_correct: true），Logic 
                   score （logic_alignment_score）should be given 80-100 points, even if there is no detailed process.If 
                   the options do not match the standard answer, a rating of no more than 40 should be given
                 - When the options are correct, the 'tutor_feedback' should focus on affirming the conclusion and 
                   briefly summarizing the mathematical principles behind the option, rather than criticizing the lack 
                   of process.
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

        # Call the core to generate logic
        return self.generate(
            prompt=prompt,
            image_bytes=student_work_image,
            temperature=0.3,
            response_mime_type="application/json"
        )
