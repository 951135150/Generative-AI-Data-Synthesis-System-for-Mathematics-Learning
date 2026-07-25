"""
Core Generation Logic - T2P System (Complex Synthesis Version)
核心优化：
1. 废弃 Exam 试卷流水线，改为“单一核心锚点 + 跨知识点融合”的大题合成模式。
2. 引入针对 429 RESOURCE_EXHAUSTED 的动态退避重试机制。
3. 强化自愈反馈循环，确保 Exam 模式下的多步综合题逻辑严密。
4. 修复：不再强制在 Exam 模式中将题型改为 calculation，保留用户选择的题型。
"""
import time
import json
import random
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

# 导入业务模块
from src.config import Config
from src.gemini_client import GeminiClient
from src.prompt_builder import PromptBuilder
from src.postprocessor import PostProcessor
from src.evaluator import QualityEvaluator

logger = logging.getLogger(__name__)

class ProblemGenerator:
    """题目生成器 - 针对深度综合题优化的新版本"""

    def __init__(self, data_loader, gemini_client=None):
        """初始化生成器"""
        self.data_loader = data_loader
        self.gemini_client = gemini_client or GeminiClient()

        # 初始化核心组件
        self.prompt_builder = PromptBuilder(data_loader)
        self.postprocessor = PostProcessor()
        self.evaluator = QualityEvaluator(data_loader, gemini_client=self.gemini_client)

    def _sample_topics(self, topics: List[str], mode: str) -> List[str]:
        """
        动态主题采样策略：
        - Drill: 保持原样。
        - Exam: 选取第一个为核心，随机选 1-2 个为关联背景。
        """
        if not topics: return []
        if mode == "drill":
            return topics[:1] # Drill 模式聚焦单一知识点

        # Exam 模式融合逻辑
        main_topic = topics[0]
        others = [t for t in topics[1:] if t != main_topic]

        # 随机抽取 1-2 个关联知识点进行融合
        related_count = random.randint(1, min(2, len(others))) if others else 0
        related = random.sample(others, related_count) if others else []

        return [main_topic] + related

    def generate_one(self, topics: List[str], mode: str = "drill",
                     difficulty: int = 3, temperature: float = None,
                     question_type: str = "mcq") -> Optional[Dict]:
        """
        生成入口：
        - 统一调用带自愈逻辑的生成方法。
        - 不再强制在 Exam 模式下覆盖题型，完全保留用户选择。
        """
        # 直接使用传入的 question_type，不再因为 exam 而强制改为 calculation
        q_type = question_type

        # 处理 429 等配额问题的外层重试与退避
        return self._generate_with_retry_logic(
            topics=topics,
            mode=mode,
            difficulty=difficulty,
            temperature=temperature,
            question_type=q_type
        )

    def _generate_with_retry_logic(self, topics, mode, difficulty, temperature, question_type) -> Optional[Dict]:
        """具备自愈反馈与配额避让逻辑的核心生成函数"""
        max_retries = Config.MAX_RETRIES
        current_feedback = ""

        # 采样当前任务的知识点组合
        active_topics = self._sample_topics(topics, mode)

        for attempt in range(max_retries):
            try:
                logger.info(f"任务尝试 {attempt + 1}/{max_retries} | 模式: {mode} | 核心: {active_topics[0]}")

                # 1. 构建提示词
                # 如果是 Exam 模式，在反馈中额外注入融合指令
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

                # 2. 调用 API (增加针对 429 的预处理)
                response = self.gemini_client.generate(
                    prompt,
                    temperature=temperature or (0.8 if mode == "exam" else 0.5)
                )

                if not response:
                    continue

                # 3. 后处理与解析
                problem = self.postprocessor.process(response, active_topics[0])
                if not problem:
                    logger.warning("JSON 解析失败，准备重试...")
                    continue

                # 4. 填充元数据
                problem.update({
                    'generated_at': datetime.now().isoformat(),
                    'mode': mode,
                    'question_type': question_type,
                    'target_difficulty': difficulty,
                    'core_topic': active_topics[0],
                    'integrated_topics': active_topics
                })

                # 5. 质量评估
                result = self.evaluator.evaluate(problem, active_topics)
                problem['evaluation'] = result.__dict__

                if result.passed:
                    logger.info(f"✅ 生成成功 (Score: {result.score})")
                    return problem
                else:
                    # 自愈逻辑：将 AI 评审意见作为下一轮的反馈
                    current_feedback = f"Previous Attempt Flaw: {result.ai_feedback}"
                    logger.warning(f"⚠️ 质量评估未通过: {result.ai_feedback}")
                    # 线性退避
                    time.sleep(2 * (attempt + 1))

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    # 关键：针对 429 实施阶梯式静默
                    wait_sec = 30 * (attempt + 1)
                    logger.error(f"🚨 触发配额限制 (429)。由于节点压力大，强制静候 {wait_sec}s...")
                    time.sleep(wait_sec)
                else:
                    logger.error(f"生成过程异常: {err_msg}")
                    time.sleep(5)

        return None

    def generate_batch(self, topics: List[str], num: int = 5,
                       mode: str = "drill", difficulty: int = 3,
                       question_type: str = "mcq") -> List[Dict]:
        """执行批量任务逻辑"""
        batch_result = []
        logger.info(f"===== 批量任务启动 | 模式: {mode.upper()} | 目标数: {num} =====")

        for i in range(num):
            logger.info(f"--- 进度: {i+1}/{num} ---")

            # 每次生成动态微调温度，增加题目多样性
            dynamic_temp = Config.DEFAULT_TEMPERATURE + (i * 0.05) % 0.2

            # 注意：在 Exam 模式下，topics[0] 会作为锚点，后续 generate_one 会自动处理融合
            problem = self.generate_one(
                topics=topics,
                mode=mode,
                difficulty=difficulty,
                temperature=dynamic_temp,
                question_type=question_type
            )

            if problem:
                batch_result.append(problem)

            # 频率控制：每道题之间强制冷却，物理避让 429
            if i < num - 1:
                delay = 10 if mode == "exam" else 5
                logger.info(f"⏳ 冷却中 ({delay}s)...")
                time.sleep(delay)

        # 批次结束后的语义去重
        if len(batch_result) > 1:
            logger.info("正在执行批次语义去重...")
            unique_problems = self.postprocessor.deduplicate(batch_result)
            return unique_problems

        return batch_result