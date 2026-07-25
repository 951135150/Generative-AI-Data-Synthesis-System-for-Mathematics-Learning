"""
Prompt Builder - Core Anchor & Multi-Dimensional Fusion (V4.0)
优化内容：
1. 废弃 Exam 试卷包模式，改为生成“深度融合大题”。
2. 引入“核心锚点 + 关联知识点”的提示逻辑。
3. 强化 LaTeX 双转义与 JSON 结构的鲁棒性。
"""
import json
import random
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class PromptBuilder:
    """提示词构建器 - 支持单一知识点训练与多知识点深度融合题生成"""

    def __init__(self, data_loader):
        """
        初始化构建器
        Args:
            data_loader: GoldenDataLoader 实例
        """
        self.data_loader = data_loader

    def build_prompt(self, topics: List[str], mode: str = "drill",
                     difficulty: int = 3, question_type: str = "calculation",
                     feedback: str = "") -> str:
        """
        统一入口：构建深度融合题或专项训练提示词
        """
        if isinstance(topics, str):
            topics = [topics]

        # 校验 question_type 是否合法
        valid_types = ["calculation", "mcq", "fill_in"]
        if question_type not in valid_types:
            logger.warning(f"⚠️ Invalid question_type '{question_type}', defaulting to 'calculation'")
            question_type = "calculation"

        # 1. 根据模式构建基础 Prompt
        if mode == "exam":
            # 在 Exam 模式下，第一个 topic 为核心锚点，其余为关联知识点
            anchor_topic = topics[0] if topics else "Calculus"
            related_topics = topics[1:] if len(topics) > 1 else []
            prompt = self._build_fusion_exam_prompt(anchor_topic, related_topics, difficulty)
        else:
            target_topic = topics[0] if topics else "Calculus Fundamentals"
            prompt = self._build_drill_prompt(target_topic, difficulty, question_type)

        # 2. 注入自愈反馈 (Self-healing)
        if feedback:
            healing_block = (
                f"\n\n[!!! CRITICAL: SELF-HEALING FEEDBACK FROM PREVIOUS ATTEMPT !!!]\n"
                f"Your previous output failed evaluation: '{feedback}'\n"
                f"INSTRUCTION: Re-generate while fixing the logic/format issues. Pay special attention to LaTeX escaping and spacing."
            )
            prompt += healing_block

        return prompt

    def _get_base_role(self, is_fusion_mode: bool = False) -> str:
        role_type = "Senior Mathematics Curriculum Designer (Fusion Specialist)" if is_fusion_mode else "Calculus Pedagogy Researcher"
        return (
            f"ROLE: You are a {role_type}. "
            "Your goal is to generate mathematically rigorous, logically consistent, and pedagogically sound materials."
        )

    def _get_logic_guardrails(self) -> str:
        return (
            "\n[STRICT MATHEMATICAL LOGIC RULES]:\n"
            "1. NUMERICAL VERIFICATION: Ensure problems are solvable with clean results (prefer integers or simple fractions).\n"
            "2. GEOMETRIC CONSISTENCY: Verify function intersections and ensure area/volume values are positive.\n"
            "3. NO HALLUCINATION: All LaTeX must be syntactically correct and parsable."
        )

    def _get_latex_constraints(self) -> str:
        """统一且严格的 LaTeX 格式约束"""
        return (
            "\n[STRICT LATEX & FORMATTING CONSTRAINTS]:"
            "\n1. ESCAPING: Inside JSON strings, use DOUBLE BACKSLASHES for all commands (e.g., '\\\\int', '\\\\frac')."
            "\n2. ENVIRONMENTS: For 'cases' or 'aligned', use FOUR BACKSLASHES for line breaks (e.g., '... \\\\\\\\ ...')."
            "\n3. DELIMITERS: Use ONLY single `$` for inline math and `$$` for block math. NEVER use `\\(`, `\\)`, `\\[`, or `\\]`."
            "\n4. MANDATORY SPACING: Leave a visible space between text and math delimiters (e.g., 'Let $ f(x) $ be')."
            "\n5. NO LAYOUT MACROS: NEVER use `\\\\quad`, `\\\\qquad`, or `\\\\text` for visual layout."
        )

    def _build_drill_prompt(self, topic: str, difficulty: int, question_type: str) -> str:
        """专项训练模式：关注单一知识点的深度"""
        prompt_parts = [
            self._get_base_role(is_fusion_mode=False),
            f"\nTASK: Generate ONE {question_type.upper()} problem for the topic: '{topic}'.",
            f"DIFFICULTY LEVEL: {difficulty}/5.",
            self._get_logic_guardrails(),
            self._get_single_output_schema(topic, question_type)
        ]
        return "\n".join(prompt_parts)

    def _build_fusion_exam_prompt(self, anchor: str, related: List[str], difficulty: int) -> str:
        """深度融合模式：核心锚点 + 多维关联"""
        related_str = ", ".join(related) if related else "applicable cross-domain concepts"

        prompt_parts = [
            self._get_base_role(is_fusion_mode=True),
            f"\nTASK: Create ONE high-order INTEGRATED problem.",
            f"CORE ANCHOR TOPIC: '{anchor}'",
            f"MANDATORY RELATED CONCEPTS: [{related_str}]",
            f"TARGET DIFFICULTY: {difficulty}/5.",
            self._get_logic_guardrails(),
            "\n[FUSION INSTRUCTIONS]:",
            "1. THEME: The problem must start with the Core Anchor but require the Related Concepts to fully solve.",
            "2. STRUCTURE: Use a multi-part structure (e.g., Part a, Part b) where Part b relies on the result or concept of Part a.",
            "3. COMPLEXITY: Focus on the transition between concepts (e.g., finding a derivative to use in a related rates application).",
            self._get_single_output_schema(f"{anchor} (Fused)", "calculation")
        ]
        return "\n".join(prompt_parts)

    def _get_single_output_schema(self, topic_str: str, question_type: str) -> str:
        """定义单道题目的标准 JSON 结构（同时兼容 Drill 和 Fusion 模式）"""
        schema = {
            "id": "T2P_GEN_1",
            "topic": topic_str,
            "problem_statement": "LaTeX text describing the problem",
            "question_type": question_type,
            "difficulty": 0,  # 0-5
            "solution": "Detailed multi-step LaTeX solution",
            "scaffolding": [
                {"step": 1, "hint": "Conceptual hint for the first hurdle"},
                {"step": 2, "hint": "Procedural hint for the calculation"}
            ],
            "integration_analysis": "Explanation of how different topics are fused here (Only for fusion mode)"
        }

        if question_type == "mcq":
            schema["options"] = {"A": "", "B": "", "C": "", "D": ""}
            schema["answer"] = "A"
        elif question_type == "fill_in":
            schema["problem_statement"] = "Problem text with [BLANK_1] and [BLANK_2]"
            schema["correct_values"] = ["val1", "val2"]

        return (
            "\n[STRICT OUTPUT RULE]: RETURN ONLY RAW JSON. NO MARKDOWN. NO PREFACE."
            f"\nJSON STRUCTURE:\n{json.dumps(schema, indent=2)}"
            f"\n{self._get_latex_constraints()}"
        )