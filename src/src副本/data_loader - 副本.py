"""
黄金数据集加载器 - 导师审计增强版 (支持全域索引与动态检索)
"""
import json
import random
from typing import Dict, List, Optional, Union
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class GoldenDataLoader:
    """
    黄金数据集加载器
    1. 支持多级主题索引与模糊匹配
    2. 支持从历史生成结果中反向检索题目 (用于视觉批改)
    """

    def __init__(self, data_path: str):
        """
        初始化加载器
        Args:
            data_path: 黄金数据集JSON文件路径
        """
        self.data_path = Path(data_path)
        self.dataset = None
        self.problems = []
        self.topics_map = {}  # 结构: { "Topic Name": [problem_dict, ...] }
        self.load()

    def load(self):
        """加载初始黄金数据集"""
        try:
            if not self.data_path.exists():
                logger.error(f"❌ 未找到数据集文件: {self.data_path}")
                return

            with open(self.data_path, 'r', encoding='utf-8') as f:
                self.dataset = json.load(f)

            # 提取题目列表
            if isinstance(self.dataset, dict) and 'problems' in self.dataset:
                self.problems = self.dataset['problems']
            elif isinstance(self.dataset, list):
                self.problems = self.dataset
            else:
                self.problems = []

            # 重新构建主题索引
            self._build_topic_map()

            logger.info(f"✅ 初始数据集加载成功：共 {len(self.problems)} 道题，"
                        f"已映射 {len(self.topics_map)} 个可用主题索引")

        except Exception as e:
            logger.error(f"❌ 加载数据集失败: {str(e)}")
            raise

    def _build_topic_map(self):
        """按大类和子类同时构建索引，并清理空格"""
        self.topics_map = {}
        for p in self.problems:
            main_topic = str(p.get('topic', 'unknown')).strip()
            sub_topic = str(p.get('sub_topic', '')).strip()

            # 1. 映射到大类
            if main_topic not in self.topics_map:
                self.topics_map[main_topic] = []
            self.topics_map[main_topic].append(p)

            # 2. 如果子类存在且不同，也映射到子类
            if sub_topic and sub_topic != main_topic:
                if sub_topic not in self.topics_map:
                    self.topics_map[sub_topic] = []
                self.topics_map[sub_topic].append(p)

    def find_problem_by_id(self, problem_id: str, output_dir: Optional[Path] = None) -> Optional[Dict]:
        """
        核心新增：全域检索题目，同时支持 problem_id 和 id 字段。
        批改端通过此方法找回题目的 solution 和 scaffolding。

        Args:
            problem_id: 题目唯一ID
            output_dir: 生成结果的输出目录 (用于寻找非种子题)
        """
        # 1. 首先在内存中的黄金题库里找
        for p in self.problems:
            if p.get('problem_id') == problem_id or p.get('id') == problem_id:
                return p

        # 2. 如果没找到，尝试在输出目录下检索生成的批次文件或单独题目文件
        if output_dir and output_dir.exists():
            logger.info(f"🔍 在输出目录 {output_dir} 中动态检索题目 {problem_id}...")
            # 遍历目录下所有 .json 文件
            for json_file in output_dir.glob("*.json"):
                # 跳过历史摘要文件
                if json_file.name == "generation_history.json":
                    continue
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # 情况 A：文件本身就是一个题目字典，检查 problem_id 或 id
                    if isinstance(data, dict):
                        if data.get('problem_id') == problem_id or data.get('id') == problem_id:
                            logger.info(f"✨ 在单独题目文件 {json_file.name} 中找回题目存档")
                            return data

                    # 情况 B：文件包含 problems 列表（批次文件）
                    target_list = data.get('problems', []) if isinstance(data, dict) else data
                    if isinstance(target_list, list):
                        for p in target_list:
                            if isinstance(p, dict):
                                if p.get('problem_id') == problem_id or p.get('id') == problem_id:
                                    logger.info(f"✨ 在历史批次 {json_file.name} 中找回题目存档")
                                    return p
                except Exception as e:
                    logger.debug(f"读取文件 {json_file.name} 失败: {e}")
                    continue

        logger.warning(f"⚠️ 无法找到 ID 为 {problem_id} 的题目数据，批改中止。")
        return None

    def get_topics(self) -> List[str]:
        """获取所有可用主题名称"""
        return list(self.topics_map.keys())

    def get_main_topics(self) -> List[str]:
        """获取唯一大类主题"""
        main_topics = set()
        for p in self.problems:
            topic = p.get('topic')
            if topic:
                main_topics.add(topic.strip())
        return sorted(list(main_topics))

    def get_examples(self, topic: str, num_examples: int = 2) -> List[Dict]:
        """获取示例题目 (带模糊匹配逻辑)"""
        search_key = topic.strip()
        examples = self.topics_map.get(search_key)

        if not examples:
            for existing_key in self.topics_map.keys():
                if search_key.lower() in existing_key.lower() or \
                   existing_key.lower() in search_key.lower():
                    examples = self.topics_map[existing_key]
                    break

        if not examples:
            return []

        sample_size = min(num_examples, len(examples))
        return random.sample(examples, sample_size)

    def format_example(self, problem: Dict) -> str:
        """格式化为 JSON 字符串"""
        return json.dumps(problem, indent=2, ensure_ascii=False)