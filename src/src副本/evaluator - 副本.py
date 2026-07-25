"""
Quality Evaluator - Intelligent & Robust Version (V4.1)
针对深度融合模式优化的审计引擎：
1. 强化跨知识点连接逻辑 (Concept Integration) 的权重。
2. 引入逻辑断层扫描，确保多步综合题的严密性。
3. 增强 JSON 安全提取与防御性清洗，适配 Gemini 2.5 Pro。
4. 【核心修复】：彻底解耦 Drill 模式的准入判定，豁免单知识点题目的融合分要求。
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from src.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

@dataclass
class EvaluationResult:
    """评估结果数据类"""
    score: float
    dimensions: Dict[str, float]
    issues: List[str]
    passed: bool
    ai_feedback: str = ""

class QualityEvaluator:
    """智能质量评估器 - 负责 T2P 系统的闭环质量控制"""

    def __init__(self, golden_data_loader=None, gemini_client=None):
        self.golden_loader = golden_data_loader
        self.gemini_client = gemini_client or GeminiClient()

        # 权重分配：在综合模式下，数学逻辑与知识点融合是核心
        self.weights = {
            'structure': 0.10,          # 基础 JSON 结构
            'math_logic': 0.35,         # 数学逻辑准确性 (核心)
            'scaffolding': 0.15,        # 支架式教学质量
            'pedagogical_alignment': 0.15, # 教育学原则对齐
            'concept_integration': 0.15, # 跨知识点融合深度
            'originality': 0.10          # 原创性
        }

    def _extract_json(self, text: str) -> Dict:
        """从模型返回的文本中安全提取 JSON"""
        try:
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```json\s*|```$', '', text, flags=re.MULTILINE)

            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return self._clean_ai_json(data)
            return {}
        except Exception as e:
            logger.warning(f"JSON 提取失败: {e}")
            return {}

    def _clean_ai_json(self, data: Dict) -> Dict:
        """防御性清洗：将 AI 返回的 null 转换为安全的默认值"""
        if not isinstance(data, dict):
            return {}

        cleaned = {}
        for k, v in data.items():
            if v is None:
                if 'score' in k:
                    cleaned[k] = 0
                elif 'is_' in k or 'correct' in k:
                    cleaned[k] = False
                else:
                    cleaned[k] = "N/A"
            else:
                cleaned[k] = v
        return cleaned

    def _evaluate_with_llm(self, problem: Dict, expected_topics: List[str]) -> Dict[str, Any]:
        """利用 AI 进行专家级评审"""
        anchor = expected_topics[0] if expected_topics else "Unknown"
        related = expected_topics[1:] if len(expected_topics) > 1 else []

        # 提示词优化：明确告知 Auditor，如果是 Drill 模式，Integration 0 分是合理的
        review_prompt = f"""
        [ROLE] Senior Mathematics Education Auditor
        [TASK] Critically evaluate this calculus problem.
        
        [CONTEXT]
        Core Anchor Topic: {anchor}
        Related Concepts: {related}
        
        [PROBLEM DATA]
        {json.dumps(problem, indent=2)}

        [AUDIT RUBRIC]
        1. MATH ACCURACY: Is the solution logically sound?
        2. CONCEPT FUSION: Meaningful link between {anchor} and {related}? (Note: If this is a single-topic DRILL, 0 is acceptable).
        3. SCAFFOLDING: Do hints guide without giving away the answer?
        4. LOGICAL CONTINUITY: Do steps follow logically?

        [OUTPUT FORMAT] Return ONLY a RAW JSON object:
        {{
            "math_logic_score": 0-100,
            "pedagogical_score": 0-100,
            "integration_score": 0-100,
            "is_mathematically_correct": true/false,
            "logical_gap_detected": true/false,
            "critical_flaw": "Specific description",
            "improvement_suggestion": "Concrete action"
        }}
        """
        try:
            response = self.gemini_client.generate(review_prompt, temperature=0.1)
            return self._extract_json(response)
        except Exception as e:
            logger.error(f"AI 评审连接异常: {e}")
            return {
                "is_mathematically_correct": False,
                "math_logic_score": 0,
                "pedagogical_score": 0,
                "integration_score": 0,
                "critical_flaw": f"Evaluation Pipeline Error: {str(e)}"
            }

    def evaluate(self, problem: Dict, target_topics: List[str] = None) -> EvaluationResult:
        """执行综合审计流程"""
        dimensions = {}
        all_issues = []

        # 识别当前模式
        current_mode = problem.get('mode', 'drill').lower()

        # 1. 结构与完整性校验
        required = ['problem_statement', 'scaffolding', 'solution', 'integration_analysis']
        missing_fields = [f for f in required if f not in problem or not problem[f]]
        struct_score = 100 - (len(missing_fields) * 25)
        dimensions['structure'] = max(0, struct_score)
        if missing_fields:
            all_issues.append(f"Missing mandatory fields: {missing_fields}")

        # 2. AI 深度语义审计
        ai_review = self._evaluate_with_llm(problem, target_topics or [])

        dimensions['math_logic'] = float(ai_review.get('math_logic_score') or 0)
        dimensions['pedagogical_alignment'] = float(ai_review.get('pedagogical_score') or 0)
        dimensions['scaffolding'] = float(ai_review.get('pedagogical_score') or 0)
        dimensions['concept_integration'] = float(ai_review.get('integration_score') or 0)

        # 3. 原创性检查
        dimensions['originality'] = 100.0
        if self.golden_loader and problem.get('problem_statement'):
            statement_snippet = problem['problem_statement'][:40]
            for golden_p in self.golden_loader.problems[:10]:
                if statement_snippet in golden_p.get('problem_statement', ''):
                    dimensions['originality'] = 30.0
                    all_issues.append("High similarity detected with Golden Dataset.")
                    break

        # 4. 最终加权汇总
        total_score = sum(dimensions[dim] * self.weights.get(dim, 0) for dim in dimensions)

        # 5. 准入判定 (核心逻辑修正)
        pass_threshold = 60.0 if current_mode == 'drill' else 75.0
        is_correct = ai_review.get('is_mathematically_correct', False)
        is_logical = not ai_review.get('logical_gap_detected', True)

        # 分模式判定准入条件
        if current_mode == 'drill':
            # --- DRILL 模式准入条件：豁免融合要求 ---
            # 只要总分过线、数学正确、逻辑通顺、结构完整即认为 Passed
            passed = (
                total_score >= pass_threshold and
                is_correct and
                is_logical and
                dimensions['structure'] >= 75
            )
        else:
            # --- EXAM/FUSION 模式准入条件：维持高标准 ---
            # 必须满足融合分硬指标 (>= 50)
            passed = (
                total_score >= pass_threshold and
                is_correct and
                is_logical and
                dimensions['structure'] >= 75 and
                dimensions['concept_integration'] >= 50.0
            )

        # 6. 构建反馈
        flaw = ai_review.get('critical_flaw') or "None"
        suggestion = ai_review.get('improvement_suggestion') or "N/A"

        feedback = (
            f"Status: {'Passed' if passed else 'Failed'} | "
            f"Score: {total_score:.1f}/{pass_threshold} | "
            f"Mode: {current_mode.upper()} | "
            f"Flaw: {flaw} | "
            f"Suggestion: {suggestion}"
        )

        if not is_correct:
            all_issues.append("CRITICAL: Mathematical logic error.")
        if not is_logical:
            all_issues.append("LOGIC GAP: Disconnected steps.")

        return EvaluationResult(
            score=round(total_score, 1),
            dimensions=dimensions,
            issues=all_issues,
            passed=passed,
            ai_feedback=feedback
        )