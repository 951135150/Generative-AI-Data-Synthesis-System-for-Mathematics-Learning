import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import numpy as np
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserSession:
    """
    UserSession 模块：管理用户学习生命周期，包含可视化能力。
    核心功能：学习路径导航、关卡晋升、时间追踪、持久化存储及学情图表生成。
    适配版本：Calculus Golden Dataset V3
    """

    def __init__(self, user_id: str, data_dir: str = "data/users"):
        self.user_id = user_id
        # 获取项目根目录
        base_path = Path(__file__).resolve().parent.parent
        self.storage_path = base_path / data_dir / f"{user_id}_progress.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # --- 核心修改：动态加载 V3 数据集 ---
        # 优先读取环境变量，否则读取 data 目录下的 v3 版本
        env_path = os.getenv("GOLDEN_DATASET_PATH")
        dataset_path = Path(env_path) if env_path else base_path / "data" / "golden_dataset_v3.json"

        logger.info(f"📅 正在基于数据集加载 Roadmap: {dataset_path.name}")
        self.roadmap = self._get_topics_from_dataset(dataset_path)

        self.progress = self._load_progress()
        self.session_start_time = None

    def _get_topics_from_dataset(self, path: Path) -> List[str]:
        """从 V3 数据集中动态提取所有主题，保持原始出现顺序"""
        try:
            if not path.exists():
                raise FileNotFoundError(f"找不到数据集文件: {path}")

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                topics = []
                # V3 数据集的题目存放在 'problems' 键下
                for p in data.get("problems", []):
                    t = p.get("topic")
                    if t and t not in topics:
                        topics.append(t)

                if not topics:
                    logger.warning("⚠️ 数据集中未提取到任何 Topic，请检查 JSON 格式。")
                return topics
        except Exception as e:
            logger.error(f"❌ 无法读取 V3 数据集生成 Roadmap: {e}")
            # 兜底 Roadmap (V3 核心主题)
            return ["Limits and Continuity", "Derivatives", "Integrals", "Vector Calculus"]

    def _load_progress(self) -> Dict:
        """加载或初始化用户进度数据，支持从旧版本 Roadmap 平滑迁移"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保 V3 中的所有新 Topic 都在用户进度中初始化
                    if "topics_status" not in data:
                        data["topics_status"] = {}

                    for topic in self.roadmap:
                        if topic not in data["topics_status"]:
                            data["topics_status"][topic] = {
                                "mastery_score": 0.0,
                                "current_level": 1,
                                "completed_count": 0
                            }
                    return data
            except Exception as e:
                logger.warning(f"读取进度文件失败，重新初始化: {e}")

        # 初始化新用户结构
        return {
            "metadata": {
                "user_id": self.user_id,
                "join_date": datetime.now().strftime("%Y-%m-%d"),
                "total_minutes": 0.0,
                "dataset_version": "V3"
            },
            "topics_status": {
                topic: {
                    "mastery_score": 0.0,  # 熟练度：0.0 到 1.0
                    "current_level": 1,  # 关卡：1(基础), 2(进阶), 3(综合/Exam)
                    "completed_count": 0
                } for topic in self.roadmap
            },
            "learning_history": []
        }

    def start_learning(self):
        """开始学习会话"""
        self.session_start_time = time.time()
        logger.info(f"🔔 用户 {self.user_id} 的 V3 学习会话已启动。")

    def stop_learning(self):
        """结束会话并持久化时间记录"""
        if self.session_start_time:
            duration = (time.time() - self.session_start_time) / 60
            self.progress["metadata"]["total_minutes"] += round(duration, 2)
            self.session_start_time = None
            self.save()

    def save(self):
        """保存进度到本地 JSON"""
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.progress, f, indent=4, ensure_ascii=False)

    def get_current_task_params(self) -> Dict:
        """自适应路径算法：基于 V3 Roadmap 寻找首个未达标的主题"""
        for topic in self.roadmap:
            status = self.progress["topics_status"].get(topic)
            if not status: continue

            if status["mastery_score"] < 0.85:
                level = status["current_level"]
                # 难度策略：L1 -> Diff 2, L2 -> Diff 3, L3 -> Diff 4/5
                difficulty = 2 if level == 1 else (3 if level == 2 else 4)
                mode = "drill" if level < 3 else "exam"

                return {
                    "topic": topic,
                    "difficulty": difficulty,
                    "mode": mode,
                    "level": level
                }
        # 全关卡达成后的挑战模式
        return {"topic": self.roadmap[-1], "difficulty": 5, "mode": "exam", "level": 3}

    def record_result(self, topic: str, score: float, is_passed: bool):
        """更新成绩、平滑计算熟练度并处理等级晋升"""
        # 兼容性处理：尝试匹配 V3 规范化的 Topic 名称
        target_topic = None
        if topic in self.progress["topics_status"]:
            target_topic = topic
        else:
            # 模糊匹配 (防止 AI 返回的主题名称带细微差异)
            for r_topic in self.roadmap:
                if topic.lower().strip() in r_topic.lower() or r_topic.lower() in topic.lower():
                    target_topic = r_topic
                    break

        if not target_topic:
            logger.warning(f"⚠️ 无法识别主题 '{topic}'，成绩未记录。")
            return

        status = self.progress["topics_status"][target_topic]

        # EMA 熟练度算法 (保持平滑增长)
        old_mastery = status["mastery_score"]
        status["mastery_score"] = round(old_mastery * 0.4 + (score / 100) * 0.6, 2)
        status["completed_count"] += 1

        # 晋升逻辑：分数达标且未达满级
        if is_passed and score >= 80 and status["current_level"] < 3:
            status["current_level"] += 1
            logger.info(f"🎊 晋升！[{target_topic}] 提升至 Level {status['current_level']}")

        self.progress["learning_history"].append({
            "time": datetime.now().isoformat(),
            "topic": target_topic,
            "score": score,
            "level_at_time": status["current_level"]
        })
        self.save()

    def generate_visual_dashboard(self, save_path: str = "output/dashboard.png"):
        """生成基于 V3 进度的可视化看板"""
        out_p = Path(__file__).resolve().parent.parent / save_path
        out_p.parent.mkdir(parents=True, exist_ok=True)

        topics = self.roadmap
        if not topics: return

        # 格式化标签
        display_labels = [t.replace(" and ", " &\n") if len(t) > 12 else t for t in topics]
        mastery_scores = [self.progress["topics_status"][t]["mastery_score"] * 100 for t in topics]
        levels = [self.progress["topics_status"][t]["current_level"] for t in topics]

        fig = plt.figure(figsize=(16, 8))
        plt.suptitle(f"T2P V3 Learning Analytics - {self.user_id}", fontsize=20, fontweight='bold', y=0.98)

        # 1. 雷达图 (熟练度分布)
        ax1 = fig.add_subplot(121, polar=True)
        angles = np.linspace(0, 2 * np.pi, len(topics), endpoint=False).tolist()
        # 闭合环线
        scores_plot = mastery_scores + [mastery_scores[0]]
        angles_plot = angles + [angles[0]]

        ax1.fill(angles_plot, scores_plot, color='#3498DB', alpha=0.3)
        ax1.plot(angles_plot, scores_plot, color='#2980B9', linewidth=2, marker='o')
        ax1.set_xticks(angles)
        ax1.set_xticklabels(display_labels, fontsize=9)
        ax1.set_title("Mastery Overview (%)", size=14, pad=30)

        # 2. 进度条 (等级分布)
        ax2 = fig.add_subplot(122)
        colors = ['#2ECC71' if l == 3 else ('#F1C40F' if l == 2 else '#BDC3C7') for l in levels]
        bars = ax2.bar(topics, levels, color=colors, alpha=0.8, edgecolor='#2C3E50')

        ax2.set_xticks(range(len(topics)))
        ax2.set_xticklabels(display_labels, rotation=25, ha="right", fontsize=9)
        ax2.set_yticks([1, 2, 3])
        ax2.set_yticklabels(['L1: Basics', 'L2: Scaffolding', 'L3: Exam Ready'])
        ax2.set_title("Progression by Topic", size=14, pad=20)

        # 在柱状图上方标注刷题数
        for bar, t in zip(bars, topics):
            count = self.progress["topics_status"][t]["completed_count"]
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                     f'n={count}', ha='center', va='bottom', fontsize=8, fontweight='bold')

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(str(out_p), dpi=300)
        plt.close()
        logger.info(f"📊 看板图表已保存: {out_p}")

    def generate_report(self):
        """生成终端字符风格的学情报告"""
        print("\n" + "╔" + "═" * 62 + "╗")
        print(f"║ {('V3 LEARNING REPORT: ' + self.user_id).center(60)} ║")
        print("╠" + "═" * 62 + "╣")
        print(f"║ ⏱️  Total Study Time: {self.progress['metadata']['total_minutes']:<32} mins ║")
        print("╟" + "─" * 62 + "╢")

        for topic in self.roadmap:
            data = self.progress["topics_status"][topic]
            icon = "✅" if data["mastery_score"] >= 0.85 else "🏗️"
            # 进度条逻辑
            bar_len = int(data['mastery_score'] * 20)
            p_bar = "█" * bar_len + "░" * (20 - bar_len)

            # 对齐显示
            topic_disp = (topic[:25] + "..") if len(topic) > 27 else topic
            print(
                f"║ {icon} {topic_disp:<27} | L{data['current_level']} | {p_bar} {int(data['mastery_score'] * 100):>3}% ║")

        print("╚" + "═" * 62 + "╝\n")

        # 自动刷新图表
        self.generate_visual_dashboard(save_path=f"output/dashboard_{self.user_id}.png")