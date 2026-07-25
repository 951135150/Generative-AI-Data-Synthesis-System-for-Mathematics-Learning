"""
Batch Generator - Intelligent Orchestrator (V4.0.1 Integrated Version)
优化内容：
1. 适配深度融合题生成模式：将 Exam 模式由全量试卷改为多道综合大题。
2. 引入批次内锚点轮换机制：确保多知识点请求时的生成覆盖率。
3. 强化物理冷却（Cooldown）：显式避让 429 配额限制。
4. 支持 question_type 参数传递，使题型选择生效。
"""
import json
import os
import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path

# 从 src 目录导入业务模块
from src.config import Config
from src.data_loader import GoldenDataLoader
from src.gemini_client import GeminiClient
from src.generator import ProblemGenerator

logger = logging.getLogger(__name__)

class BatchGenerator:
    """批量生成与审计调度器 - T2P 系统的核心引擎"""

    def __init__(self, output_dir: str = None):
        """初始化调度器"""
        self.output_dir = Path(output_dir or Config.OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. 加载黄金数据
        self.data_loader = GoldenDataLoader(Config.GOLDEN_DATASET_PATH)

        # 2. 初始化核心客户端
        self.gemini_client = GeminiClient()

        # 3. 创建生成器
        self.generator = ProblemGenerator(self.data_loader, gemini_client=self.gemini_client)

        # 4. 维护生成历史
        self.history_file = self.output_dir / "generation_history.json"
        self.history = self._load_history()

    def _load_history(self) -> Dict:
        """加载生成历史摘要"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and 'batches' in data:
                        return data
            except Exception as e:
                logger.warning(f"⚠️ 读取历史文件失败: {e}")
        return {'batches': []}

    def _save_history(self):
        """保存生成历史摘要"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 保存历史文件失败: {e}")

    def generate(self, topics: List[str] = None, num: int = 5,
                 mode: str = "drill", difficulty: int = 3,
                 question_type: str = "calculation",   # ✅ 新增题型参数
                 batch_name: str = None) -> Dict:
        """
        执行智能题目生成流程
        """
        if not topics:
            topics = self.data_loader.get_main_topics()

        logger.info(f"🚀 任务启动 | 模式: {mode.upper()} | 目标数量: {num} | 题型: {question_type} | 核心池: {topics}")

        final_problems = []

        # --- 核心调度逻辑 ---
        for i in range(num):
            logger.info(f"--- 正在处理第 {i+1}/{num} 道题目 ---")

            # 动态调整当前任务的知识点排列
            # Exam 模式下，每次循环轮换第一个元素作为“核心锚点”
            if mode == "exam" and len(topics) > 1:
                current_topics = [topics[i % len(topics)]] + [t for t in topics if t != topics[i % len(topics)]]
            else:
                current_topics = topics

            # 动态温度微调
            temp = Config.DEFAULT_TEMPERATURE + (i * 0.05) % 0.3

            # 调用生成器
            prob = self.generator.generate_one(
                topics=current_topics,
                mode=mode,
                difficulty=difficulty,
                temperature=temp,
                question_type=question_type   # ✅ 传递题型
            )

            if prob:
                final_problems.append(prob)

            # --- 物理冷却逻辑 (避让 429) ---
            if i < num - 1:
                # Exam 模式由于 Token 消耗大，冷却时间延长
                delay = 12 if mode == "exam" else 5
                logger.info(f"⏳ 物理冷却中，等待 {delay} 秒后继续...")
                time.sleep(delay)

        # --- 后处理：语义去重 ---
        if final_problems and len(final_problems) > 1:
            original_count = len(final_problems)
            final_problems = self.generator.postprocessor.deduplicate(final_problems)
            if len(final_problems) < original_count:
                logger.info(f"♻️ 语义去重引擎已过滤 {original_count - len(final_problems)} 道高度相似题目")

        # 构建批次详情
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch_result = {
            'batch_id': batch_id,
            'batch_name': batch_name or f"{mode}_{batch_id[-6:]}",
            'mode': mode,
            'question_type': question_type,   # ✅ 记录题型
            'generated_at': datetime.now().isoformat(),
            'target_topics': topics,
            'difficulty_setting': difficulty,
            'total_generated': len(final_problems),
            'problems': final_problems
        }

        # 持久化存储结果
        output_file = self.output_dir / f"{batch_id}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(batch_result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 批次文件保存失败: {e}")

        # 更新摘要历史
        self.history['batches'].append({
            'batch_id': batch_id,
            'mode': mode,
            'topics': topics,
            'total_generated': len(final_problems),
            'generated_at': batch_result['generated_at']
        })
        self._save_history()

        return batch_result

    def review_student_submission(self, problem_id: str, image_path: str, is_exam_mode: bool = False) -> Dict:
        """智能导师批改接口 (保持现状)"""
        problem_data = None
        for p in self.data_loader.problems:
            if p.get('problem_id') == problem_id:
                problem_data = p
                break

        if not problem_data:
            logger.error(f"❌ 审计中止：未能在数据集中找到 ID 为 {problem_id} 的参考答案")
            return {"error": "Target problem data missing from loader."}

        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            logger.error(f"❌ 图片读取失败: {e}")
            return {"error": f"Image read error: {str(e)}"}

        logger.info(f"🕵️ 启动 AI 导师审计 | 题目: {problem_id}")
        raw_review = self.gemini_client.mentor_review(
            student_work_image=image_bytes,
            problem_data=problem_data,
            is_exam_mode=is_exam_mode
        )

        try:
            cleaned_review = raw_review.strip().replace("```json", "").replace("```", "")
            return json.loads(cleaned_review)
        except:
            return {"raw_ai_feedback": raw_review}

    def get_statistics(self) -> Dict:
        """获取系统运行统计摘要（增强版）"""
        all_batches = self.history.get('batches', [])
        stats = {
            'total_batches': len(all_batches),
            'total_problems': sum(b.get('total_generated', 0) for b in all_batches),
            'mode_distribution': {
                'drill': len([b for b in all_batches if b.get('mode') == 'drill']),
                'exam': len([b for b in all_batches if b.get('mode') == 'exam'])
            },
            'performance': { 'avg_quality_score': 0.0 }
        }

        scores = []
        for batch in all_batches:
            batch_file = self.output_dir / f"{batch['batch_id']}.json"
            if batch_file.exists():
                try:
                    with open(batch_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for p in data.get('problems', []):
                            s = p.get('evaluation', {}).get('score')
                            if s is not None: scores.append(float(s))
                except: continue

        if scores:
            stats['performance']['avg_quality_score'] = round(sum(scores) / len(scores), 2)
        return stats