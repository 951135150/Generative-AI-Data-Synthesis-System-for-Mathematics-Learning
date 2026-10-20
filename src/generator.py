"""
Core Generation Logic - Calculus Atelier (Complex Synthesis Version)
Core optimizations:
1. Deprecated Exam paper pipeline, changed to "single core anchor + cross-knowledge-point fusion" comprehensive problem synthesis mode.
2. Introduced dynamic backoff retry mechanism for 429 RESOURCE_EXHAUSTED.
3. Strengthened self-healing feedback loop to ensure logical rigor of multi-step comprehensive problems in Exam mode.
4. Fix: No longer force question type to change to calculation in Exam mode, preserving user-selected question type.
"""
import time
import json
import random
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# Import business modules
from src.config import Config
from src.llm_client import LLMClient
from src.prompt_builder import PromptBuilder
from src.postprocessor import PostProcessor
from src.evaluator import QualityEvaluator
from src.rag import get_retriever
from src.rag.service import evidence_prompt

logger = logging.getLogger(__name__)

class ProblemGenerator:
    """Problem generator - New version optimized for deep comprehensive problems"""

    def __init__(self, data_loader, llm_client=None):
        """Initialize generator"""
        self.data_loader = data_loader
        self.llm_client = llm_client or LLMClient()

        # Initialize core components
        self.prompt_builder = PromptBuilder(data_loader)
        self.postprocessor = PostProcessor()
        self.evaluator = QualityEvaluator(data_loader, llm_client=self.llm_client)

    def _sample_topics(self, topics: List[str], mode: str) -> List[str]:
        """
        Dynamic topic sampling strategy:
        - Drill: Keep as-is.
        - Exam: Select the first as core, randomly pick 1-2 as related context.
        """
        if not topics: return []
        if mode == "drill":
            return topics[:1] # Drill mode focuses on a single knowledge point

        # Exam mode fusion logic
        main_topic = topics[0]
        others = [t for t in topics[1:] if t != main_topic]

        # Randomly select 1-2 related knowledge points for fusion
        related_count = random.randint(1, min(2, len(others))) if others else 0
        related = random.sample(others, related_count) if others else []

        return [main_topic] + related

    def generate_one(self, topics: List[str], mode: str = "drill",
                     difficulty: int = 3, temperature: float = None,
                     question_type: str = "mcq") -> Optional[Dict]:
        """
        Generation entry point:
        - Uniformly calls the generation method with self-healing logic.
        - No longer forces override of question type in Exam mode, fully preserves user selection.
        """
        # Directly use the passed question_type, no longer force change to calculation due to exam
        q_type = question_type

        # Outer retry and backoff for handling 429 quota issues
        return self._generate_with_retry_logic(
            topics=topics,
            mode=mode,
            difficulty=difficulty,
            temperature=temperature,
            question_type=q_type
        )

    def _generate_with_retry_logic(self, topics, mode, difficulty, temperature, question_type) -> Optional[Dict]:
        """Core generation function with self-healing feedback and quota avoidance logic"""
        max_retries = Config.MAX_RETRIES
        current_feedback = ""

        # Sample knowledge point combination for current task
        active_topics = self._sample_topics(topics, mode)
        evidence = get_retriever().retrieve(
            " ".join(active_topics), topics=active_topics, purpose="generate", exam=mode == "exam",
        )

        for attempt in range(max_retries):
            try:
                logger.info(f"Task attempt {attempt + 1}/{max_retries} | Mode: {mode} | Core: {active_topics[0]}")

                # 1. Build prompt
                # If in Exam mode, inject additional fusion instruction in feedback
                fusion_instruction = ""
                if mode == "exam" and len(active_topics) > 1:
                    fusion_instruction = f"| COMPOSITE TASK: Integrate {active_topics[1:]} into the context of {active_topics[0]}."

                prompt = self.prompt_builder.build_prompt(
                    topics=active_topics,
                    mode=mode,
                    difficulty=difficulty,
                    feedback=current_feedback + fusion_instruction,
                    question_type=question_type
                )
                prompt += evidence_prompt(evidence)
                if Config.AI_MODE == "simulation":
                    prompt += "\n[SIMULATION TASK]" + json.dumps({
                        "topic": active_topics[0], "difficulty": difficulty,
                        "question_type": question_type, "mode": mode,
                    })

                # 2. Call API (with preprocessing for 429)
                response = self.llm_client.generate(
                    prompt,
                    temperature=temperature or (0.8 if mode == "exam" else 0.5)
                )

                if not response:
                    continue

                # 3. Post-processing and parsing
                problem = self.postprocessor.process(response, active_topics[0])
                if not problem:
                    logger.warning("JSON parsing failed, preparing to retry...")
                    continue

                # 4. Fill metadata
                problem.update({
                    'topic': active_topics[0],
                    'generated_at': datetime.now().isoformat(),
                    'mode': mode,
                    'question_type': question_type,
                    'target_difficulty': difficulty,
                    'core_topic': active_topics[0],
                    'integrated_topics': active_topics
                })
                problem["retrieval"] = evidence
                problem["ai_mode"] = Config.AI_MODE
                if question_type == "mcq":
                    problem["semantic_validation_required"] = True
                if Config.AI_MODE == "simulation" and mode == "exam":
                    # A template is not a validated cross-topic exam; do not manufacture fusion scores.
                    problem["simulation_note"] = "Single-concept exam fixture; cross-topic fusion not evaluated."

                # 5. Quality evaluation
                evaluation_problem = dict(problem, mode="drill") if Config.AI_MODE == "simulation" else problem
                result = self.evaluator.evaluate(evaluation_problem, active_topics)
                problem['evaluation'] = result.__dict__
                if Config.AI_MODE == "simulation":
                    problem["evaluation"]["review_kind"] = "deterministic_fixture_check"
                    problem["evaluation"]["semantic_quality_measured"] = False
                if str(problem.get("question_type", "")).lower() == "mcq":
                    deterministic = result.deterministic_validation or {}
                    problem["answer_validation"] = {
                        "status": ("fixture_checked" if Config.AI_MODE == "simulation" else "verified") if result.passed else "rejected",
                        "answer_key": problem.get("answer"),
                        "semantic_options_checked": bool(deterministic.get("checks", {}).get("mcq_semantics_checked")),
                        "schema_check": bool(deterministic.get("schema_valid")),
                        "symbolic_check": deterministic.get(
                            "symbolic_status",
                            "not_provided",
                        ),
                        "independent_review": (
                            Config.AI_MODE != "simulation" and result.dimensions.get("answer_consistency") == 100.0
                        ),
                        "method": (
                            "offline symbolic claim and fixture option mapping; no independent model review"
                            if Config.AI_MODE == "simulation" else
                            "deterministic schema/symbolic validation plus "
                            "independent low-temperature mathematical review"
                        ),
                    }

                if result.passed:
                    logger.info(f"[PASS] Generation successful (Score: {result.score})")
                    return problem
                else:
                    # Self-healing logic: Use AI review feedback as input for next round
                    current_feedback = f"Previous Attempt Flaw: {result.ai_feedback}"
                    logger.warning(f"[WARN] Quality evaluation failed: {result.ai_feedback}")
                    # Linear backoff
                    if Config.AI_MODE == "live":
                        time.sleep(2 * (attempt + 1))

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    # Critical: Implement stepped silence for 429
                    wait_sec = 30 * (attempt + 1)
                    logger.error(f"[429] Quota limit triggered. Waiting {wait_sec}s...")
                    time.sleep(wait_sec)
                else:
                    logger.error(f"Generation process exception: {err_msg}")
                    if Config.AI_MODE != "live":
                        raise
                    time.sleep(5)

        return None

    def generate_batch(self, topics: List[str], num: int = 5,
                       mode: str = "drill", difficulty: int = 3,
                       question_type: str = "mcq") -> List[Dict]:
        """Execute batch task logic"""
        batch_result = []
        logger.info(f"===== Batch task started | Mode: {mode.upper()} | Target count: {num} =====")

        for i in range(num):
            logger.info(f"--- Progress: {i+1}/{num} ---")

            # Dynamically fine-tune temperature for each generation to increase problem diversity
            dynamic_temp = Config.DEFAULT_TEMPERATURE + (i * 0.05) % 0.2

            # Note: In Exam mode, topics[0] serves as anchor, subsequent generate_one will auto-handle fusion
            problem = self.generate_one(
                topics=topics,
                mode=mode,
                difficulty=difficulty,
                temperature=dynamic_temp,
                question_type=question_type
            )

            if problem:
                batch_result.append(problem)

            # Rate control: Force cooldown between problems, physically avoid 429
            if i < num - 1 and Config.AI_MODE == "live":
                delay = 10 if mode == "exam" else 5
                logger.info(f"Cooling down ({delay}s)...")
                time.sleep(delay)

        # Semantic deduplication after batch completion
        if len(batch_result) > 1:
            logger.info("Running batch semantic deduplication...")
            unique_problems = self.postprocessor.deduplicate(batch_result)
            return unique_problems

        return batch_result
