"""
PostProcessor - V4.2 T2P 生产环境加固版 (LaTeX 渲染增强版)
主要更新：
1. 【修复定界符】统一使用正则替换，消除多重转义导致的定界符残留。
2. 【移除过度保护】清理 clean_json_text 中的反斜杠叠加，避免 `\begin` 变为 `\\begin`。
3. 【增强清洗】额外处理 LaTeX 换行符、移除无意义空格。
4. 【保持兼容】保留原有语义去重与 JSON 解析容错能力。
"""
import json
import re
import logging
import torch
import numpy as np
from typing import Dict, List, Optional, Any
from sentence_transformers import SentenceTransformer
from sentence_transformers import util

logger = logging.getLogger(__name__)

class PostProcessor:
    """后处理器 - 负责将 LLM 的原始输出转化为结构化教学数据 (支持 GPU 加速)"""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self.similarity_model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            logger.info(f"正在加载语义去重模型... (目标设备: {self.device})")
            self.similarity_model = SentenceTransformer(
                'paraphrase-multilingual-MiniLM-L12-v2',
                device=self.device
            )
            logger.info(f"✅ 语义去重引擎已就绪 [Device: {self.device.upper()}]")
        except Exception as e:
            logger.warning(f"⚠️ 语义模型加载失败，将启用文本指纹降级方案: {str(e)}")
            self.similarity_model = None

    def _sanitize_text(self, text: str) -> str:
        """
        深度清洗业务文本：解决渲染异常及 LaTeX 语法冲突
        """
        if not isinstance(text, str) or not text:
            return text

        # 1. 【核心修复】统一数学公式定界符，采用正则避免遗漏多重转义
        #    先处理 \(...\) 和 \[...\]，再处理可能因 JSON 转义产生的 \\$ 等残留
        text = re.sub(r'\\\(', '$', text)          # \( → $
        text = re.sub(r'\\\)', '$', text)          # \) → $
        text = re.sub(r'\\\[', '$$', text)         # \[ → $$
        text = re.sub(r'\\\]', '$$', text)         # \] → $$

        # 2. 【修复残留转义】清除因多重转义产生的类似 \\$、\\[、\\] 等异常符号
        text = re.sub(r'\\\\\$', '$', text)        # \\$ → $
        text = re.sub(r'\\\\\[', '$$', text)       # \\[ → $$
        text = re.sub(r'\\\\\]', '$$', text)       # \\] → $$

        # 3. 【LaTeX 环境修复】消除 \begin{cases}、\end{cases} 等前面的多余空格或反斜杠
        text = re.sub(r'\\\s+begin\{', r'\\begin{', text)
        text = re.sub(r'\\\s+end\{', r'\\end{', text)

        # 4. 【KaTeX 适配】移除 cases 环境内部的 $ 符号（数学环境内部不需要）
        if "\\begin{cases}" in text:
            def strip_dollars_in_cases(match):
                return match.group(0).replace('$', '')
            text = re.sub(r'\\begin\{cases\}.*?\\end\{cases\}', strip_dollars_in_cases, text, flags=re.DOTALL)

        # 5. 【防复读】解决 LLM 常见的公式重复幻觉
        text = re.sub(r'(\$?[\w\(\)\+\-\=\, ]{3,}\$?)\s+\1', r'\1', text)

        # 6. 【渲染清理】移除冗余的排版宏
        text = re.sub(r'\\+\[\s*\d+[a-zA-Z]+\s*\]', ' ', text)
        text = re.sub(r'\\+(quad|qquad|enspace|thickspace|vspace\{.*?\}|hspace\{.*?\})', ' ', text)

        # 7. 【粘连修复】确保公式与中文字符间有空格
        text = re.sub(r'([\u4e00-\u9fa5])\$', r'\1 $', text)
        text = re.sub(r'\$([\u4e00-\u9fa5])', r'$ \1', text)

        # 8. 【最终修整】连续空格压缩，去除首尾空白
        text = re.sub(r' +', ' ', text)
        return text.strip()

    def _recursive_sanitize(self, obj: Any) -> Any:
        """递归遍历 JSON 结构并清洗所有字符串字段"""
        if isinstance(obj, str):
            return self._sanitize_text(obj)
        elif isinstance(obj, list):
            return [self._recursive_sanitize(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._recursive_sanitize(v) for k, v in obj.items()}
        return obj

    def clean_json_text(self, text: str) -> str:
        """针对 LaTeX 反斜杠在 JSON 解析中的保护逻辑（避免额外转义）"""
        if not text:
            return ""

        # 移除 Markdown 代码块标记
        text = re.sub(r'^```json\s*|\s*```$', '', text.strip(), flags=re.MULTILINE)

        # 寻找合法的 JSON 边界
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx == -1 or end_idx == -1:
            return text
        text = text[start_idx:end_idx + 1]

        # 【关键修改】只保护双反斜杠（LaTeX 换行），不再对所有 LaTeX 命令加反斜杠
        # 原逻辑会导致 \begin → \\begin，最终前端显示为 \begin 甚至 \\begin
        text = text.replace('\\\\', '___DBL___')   # 保护已有的双反斜杠
        # 移除原来 re.sub(r'\\([a-zA-Z]+)', ...) 这一行，不再对命令额外转义
        text = text.replace('___DBL___', '\\\\')   # 恢复双反斜杠

        # 过滤不可见控制字符
        text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\r\t")
        return text

    def parse_json(self, text: str) -> Optional[Dict]:
        """增强版解析器：处理 JSON 语法错误与转义冲突"""
        cleaned = self.clean_json_text(text)
        try:
            # 尝试标准解析
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.debug(f"标准解析失败，尝试修复容错: {e}")
            try:
                # 修复末尾逗号与不规范换行
                fixed = re.sub(r',\s*([\]}])', r'\1', cleaned)
                fixed = fixed.replace('\n', '\\n').replace('\r', '')
                return json.loads(fixed)
            except Exception as final_e:
                logger.error(f"❌ JSON 解析彻底失败: {str(final_e)}")
                return None

    def _normalize_problem(self, problem: Dict) -> Dict:
        """确保字段对齐，补全缺失维度"""
        if not isinstance(problem, dict):
            return problem

        # 1. 题干映射
        if 'statement' in problem and 'problem_statement' not in problem:
            problem['problem_statement'] = problem.pop('statement')

        # 2. 答案映射
        answer_variants = ['correct_answer', 'target_answer', 'ans', 'res']
        for var in answer_variants:
            if var in problem and 'answer' not in problem:
                problem['answer'] = problem.pop(var)

        # 3. 教学支架与解析补全
        if 'analysis' in problem and 'scaffolding' not in problem:
            problem['scaffolding'] = problem.get('analysis')

        if 'solution' not in problem:
            if 'answer' in problem:
                problem['solution'] = f"标准解答: {problem['answer']}"
            elif 'correct_values' in problem:
                vals = ", ".join(map(str, problem['correct_values']))
                problem['solution'] = f"标准数值: {vals}"

        # 强制确保 problem_statement 存在
        if 'problem_statement' not in problem:
            problem['problem_statement'] = "题干解析异常，请重新生成。"

        return problem

    def process(self, raw_text: str, topic: str = None) -> Optional[Dict]:
        """主入口：执行 解析 -> 清洗 -> 对齐 -> 校验 流程"""
        data = self.parse_json(raw_text)
        if not data:
            return None

        # 1. 递归清洗文本（解决复读机与渲染冲突）
        data = self._recursive_sanitize(data)

        # 2. 模式识别处理
        exam_keys = ['section_a_mcq', 'section_b_fill_in', 'section_c_long_questions']
        if any(key in data for key in exam_keys):
            return data

        # 3. 字段标准化
        problem = self._normalize_problem(data)

        # 4. 难度与元数据修正
        try:
            d = int(problem.get('difficulty', 3))
            problem['difficulty'] = max(1, min(5, d))
        except Exception:
            problem['difficulty'] = 3

        if topic:
            problem['topic'] = topic

        return problem

    def deduplicate(self, problems: List[Dict], existing: List[Dict] = None) -> List[Dict]:
        """基于 Transformer 的语义去重（支持模型缺失降级）"""
        if not problems or self.similarity_model is None:
            return self._basic_deduplicate(problems, existing)

        new_texts = [p.get('problem_statement', '') for p in problems
                     if isinstance(p, dict) and p.get('problem_statement')]
        if not new_texts:
            return problems

        new_embeddings = self.similarity_model.encode(new_texts, convert_to_tensor=True)

        pool_embeddings = None
        if existing:
            existing_texts = [p.get('problem_statement', '') for p in existing
                              if isinstance(p, dict) and p.get('problem_statement')]
            if existing_texts:
                pool_embeddings = self.similarity_model.encode(existing_texts, convert_to_tensor=True)

        unique_problems = []
        for i, emb in enumerate(new_embeddings):
            is_duplicate = False
            if pool_embeddings is not None:
                sims = util.cos_sim(emb, pool_embeddings)[0]
                max_sim = torch.max(sims).item()
                if max_sim > self.similarity_threshold:
                    is_duplicate = True

            if not is_duplicate:
                unique_problems.append(problems[i])
                emb_unsqueezed = emb.unsqueeze(0)
                if pool_embeddings is not None:
                    pool_embeddings = torch.cat([pool_embeddings, emb_unsqueezed])
                else:
                    pool_embeddings = emb_unsqueezed

        return unique_problems

    def _basic_deduplicate(self, problems: List[Dict], existing: List[Dict] = None) -> List[Dict]:
        """文本指纹去重保底方案"""
        seen = set()
        if existing:
            for p in existing:
                if not isinstance(p, dict):
                    continue
                fp = re.sub(r'\s+', '', str(p.get('problem_statement', '')))
                seen.add(fp)

        unique = []
        for p in problems:
            if not isinstance(p, dict):
                unique.append(p)
                continue
            fp = re.sub(r'\s+', '', str(p.get('problem_statement', '')))
            if fp not in seen:
                unique.append(p)
                seen.add(fp)
        return unique