"""
Gemini Client - 导师审计增强版 (支持视觉批改、文本仿真与 429 自动避让)
"""
import logging
import time
import os
import sys
import json
from typing import Optional, Union, List, Dict
# 1. 获取当前项目下 venv 的标准包路径
# 注意：这里我们使用相对路径，确保它能自动找到你当前项目下的 venv
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_site_packages = os.path.join(current_dir, "venv", "Lib", "site-packages")

# 2. 将这个路径插入到搜索列表的第一位
if os.path.exists(venv_site_packages):
    sys.path.insert(0, venv_site_packages)
    print(f"--- 已强制挂载虚拟环境包路径: {venv_site_packages} ---")
else:
    print("--- 警告：未找到 venv 路径，请检查 venv 文件夹是否存在 ---")

# 3. 现在的 import 就会优先从 venv 里找
from src.config import Config
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiClient:
    def __init__(self):
        """初始化 Gemini 客户端 - 强制适配 Vertex AI"""
        # 1. 从 Config 类获取 Vertex AI 专用参数
        self.target_project = Config.PROJECT_ID
        self.target_location = Config.LOCATION
        self.model_name = Config.GEMINI_MODEL
        # API_KEY 在 Vertex 模式下通常不需要，但保留引用以防万一
        self.api_key = Config.API_KEY

        try:
            # 2. 核心逻辑：优先/强制使用 Vertex AI 模式
            # 如果 Config.API_KEY 为空或你希望强制使用 GCP 凭据，请确保 vertexai=True
            if not self.api_key:
                logger.info(f"☁️ 正在初始化 Vertex AI 客户端 (项目: {self.target_project})...")
                self.client = genai.Client(
                    vertexai=True,
                    project=self.target_project,
                    location=self.target_location
                )
            else:
                # 兼容模式：如果提供了 API_KEY 则走 AI Studio 路径
                logger.info("🔑 检测到 API_KEY，正在使用 API 密钥认证模式...")
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options={'api_version': 'v1alpha'}
                )

            logger.info("==========================================")
            logger.info(f"📍 节点/区域: {self.target_location}")
            logger.info(f"🆔 GCP 项目: {self.target_project}")
            logger.info(f"⚙️ 核心模型: {self.model_name}")
            logger.info("==========================================")

        except Exception as e:
            logger.error(f"❌ Gemini 客户端初始化失败，请检查 GCP 凭据或项目 ID: {str(e)}")
            raise

    def generate(self, prompt: str, image_bytes: Optional[bytes] = None,
                 mime_type: str = "image/jpeg",
                 response_mime_type: str = "application/json",
                 temperature: float = 0.5) -> Optional[str]:
        """
        核心生成方法：支持多模态输入与高可用重试逻辑
        """
        contents = []

        # 仅当 image_bytes 为二进制且非空时，才添加图像 Part
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
                task_label = "🖼️ 视觉审计" if image_bytes else "📝 文本审计/生成"
                logger.info(f"📡 {task_label} | 请求发送中 (第 {attempt + 1}/3 次尝试)...")

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=generate_config
                )

                if response and response.text:
                    return response.text

                if response.candidates and response.candidates[0].finish_reason == "SAFETY":
                    logger.error("🚨 响应被安全策略拦截。")
                    return None

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < 2:
                        wait_time = 90
                        logger.warning(f"🚨 节点繁忙 (429)。静候 {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                if attempt < 2:
                    logger.warning(f"⚠️ 临时错误: {err_msg}。5s 后重试...")
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"❌ 任务最终失败: {err_msg}")
                    raise e
        return None

    def mentor_review(self, student_work_image: Optional[bytes] = None,
                      problem_data: Dict = {},
                      is_exam_mode: bool = False,
                      student_text_answer: Optional[str] = None) -> str:
        """
        封装的导师审计接口：支持图片、纯文本或两者结合

        Args:
            student_work_image: bytes (照片二进制数据)
            problem_data: 题目元数据
            is_exam_mode: 模式开关
            student_text_answer: 选择题选项或学生输入的文本答案
        """
        scaffolding_info = "不可用（考试模式禁止提示）" if is_exam_mode else problem_data.get('scaffolding')

        # --- 智能负载构建 ---
        input_descriptions = []
        if student_work_image:
            input_descriptions.append("手写解答照片")
        if student_text_answer:
            input_descriptions.append(f"文本解答内容 (提交内容: {student_text_answer})")

        input_type_desc = " + ".join(input_descriptions) if input_descriptions else "未提交任何内容"

        mode_instruction = (
            "【模式：严格考试】\n- 严禁给出具体解法。\n- 重点指出逻辑断层。"
            if is_exam_mode else
            "【模式：启发练习】\n- 使用 Socratic 方法引导学生发现错误。"
        )

        # 构造最终发送给 AI 的 Prompt
        # --- src/gemini_client.py ---

        prompt = f"""
                你是一位专业的微积分导师。请审计学生的提交内容。
                提交类型: {input_type_desc}

                {mode_instruction}

                【参考基准】
                - 题目描述: {problem_data.get('problem_statement')}
                - 标准答案/选项: {problem_data.get('solution')} 

                【学生提交的具体内容】
                {student_text_answer if student_text_answer else "（见图片内容）"}

                【审计与评分准则 - 极其重要】
                1. **选择题特殊逻辑**：如果学生提交的内容是一个明确的选项（如 A, B, C, D）：
                   - 若选项与标准答案一致，应判定为正确（is_correct: true），逻辑分（logic_alignment_score）应给予 80-100 分，即使没有详细过程。
                   - 此时的 `tutor_feedback` 应侧重于肯定结论，并简要概括该选项背后的数学原理，而不是批评没有过程。
                2. **计算/推导题逻辑**：如果学生提交的是手写照片或长文本推导，则按原样进行逻辑对齐审计包括： 错误诊断：定位错误位置（计算、概念或公式）,完整性检查：检查是否缺少关键证明步骤。
                3. **错误诊断**：如果选项错误，请通过 Socratic 引导，询问学生在应用相关公式（如余弦定理或导数链式法则）时是否忽略了某个变量。

                【输出格式 (JSON ONLY)】
                {{
                    "is_correct": bool,
                    "logic_alignment_score": int,
                    "error_analysis": "如果是选择题且正确，请写'选项正确'；若错误，分析可能的认知偏误",
                    "tutor_feedback": "鼓励式反馈，若是正确选项，简述其逻辑 (LaTeX)",
                    "next_hint": "引导下一步思考"
                }}
                """

        # 调用核心生成逻辑
        return self.generate(
            prompt=prompt,
            image_bytes=student_work_image,
            temperature=0.3,
            response_mime_type="application/json"
        )
