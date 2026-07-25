"""
配置文件 - 管理项目路径、Vertex AI 参数及生成控制
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv


# 在这里定义一个新的 logger，这样它就不依赖 api_server 了
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class Config:
    """全局配置类"""

    # --- 基础路径配置 ---
    # Path(__file__).resolve() -> D:\PycharmBase\T2P\src\config.py
    # .parent.parent -> D:\PycharmBase\T2P
    BASE_DIR = Path(__file__).resolve().parent.parent
    BASE_DIR = Path(__file__).resolve().parent.parent
    print(f"当前识别到的项目根目录是: {BASE_DIR}")  # 运行后看控制台输出

    # --- 资源路径 ---
    # 默认指向 D:\PycharmBase\T2P\data\golden_dataset_v2.json
    GOLDEN_DATASET_PATH = os.getenv("GOLDEN_DATASET_PATH", str(BASE_DIR / "data" / "golden_dataset_v3.json"))

    # 默认指向 D:\PycharmBase\T2P\output
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "output"))

    # 默认指向 D:\PycharmBase\T2P\logs\t2p_system.log
    LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "t2p_system.log"))

    # --- Vertex AI 核心配置 ---
    # 修改后 (更安全)
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT_ID:
        logger.error("❌ 未在环境变量中找到 GOOGLE_CLOUD_PROJECT")

    # 【修改点】: 将默认区域从 europe-west1 修改为 us-central1
    LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    # 添加这一行以确保程序能读取到你的 API Key[cite: 8, 11]
    API_KEY = os.getenv("GOOGLE_API_KEY")
    # 保持使用 gemini-2.5-pro
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    # --- 模型生成控制参数 ---
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", 0.5))
    DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", 16384))
    DEFAULT_TOP_P = float(os.getenv("DEFAULT_TOP_P", 0.95))
    DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", 40))

    # --- 运行调度配置 ---
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1))
    REQUEST_DELAY = int(os.getenv("REQUEST_DELAY", 30))

    # 【建议】: 考虑到 429 风险，重试次数可以维持在 3 或增加到 5
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

    # --- 日志级别 ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        Path(cls.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(cls.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)


# 自动初始化目录
Config.ensure_dirs()