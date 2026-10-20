"""
Configuration file - Manages project paths, DeepSeek API parameters, and generation control
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv


# Define a new logger here so it doesn't depend on api_server
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class Config:
    """Global configuration class"""

    # --- Base path configuration ---
    # Path(__file__).resolve() -> <project_root>\src\config.py
    # .parent.parent -> <project_root>
    BASE_DIR = Path(__file__).resolve().parent.parent
    # External model calls are opt-in, even when an old .env contains keys.
    AI_MODE = os.getenv("AI_MODE", "simulation").strip().lower()
    ALLOW_PAID_API = os.getenv("ALLOW_PAID_API", "false").lower() == "true"
    RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
    RAG_MODEL = os.getenv("RAG_MODEL", "intfloat/multilingual-e5-small")
    RAG_MODEL_REVISION = os.getenv("RAG_MODEL_REVISION", "614241f622f53c4eeff9890bdc4f31cfecc418b3")
    RAG_CACHE_DIR = Path(os.getenv("RAG_CACHE_DIR", str(BASE_DIR / ".runtime" / "rag")))
    KNOWLEDGE_PATH = Path(os.getenv("KNOWLEDGE_PATH", str(BASE_DIR / "data" / "knowledge")))
    RAG_ALLOW_DOWNLOAD = os.getenv("RAG_ALLOW_DOWNLOAD", "false").lower() == "true"

    # --- Resource paths ---
    # Default points to <project_root>\data\golden_dataset_v2.json
    GOLDEN_DATASET_PATH = os.getenv("GOLDEN_DATASET_PATH", str(BASE_DIR / "data" / "golden_dataset_v3.json"))

    # Default points to <project_root>\output
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "output"))
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'data' / 't2p.db').as_posix()}",
    )
    MIRROR_JSON_PROGRESS = os.getenv(
        "MIRROR_JSON_PROGRESS", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    AUTH_SESSION_HOURS = int(os.getenv("AUTH_SESSION_HOURS", "24"))
    PASSWORD_PBKDF2_ITERATIONS = int(
        os.getenv("PASSWORD_PBKDF2_ITERATIONS", "600000")
    )

    # --- OpenTelemetry ---
    OTEL_ENABLED = os.getenv("OTEL_ENABLED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "t2p-api")
    OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    OTEL_CONSOLE_EXPORTER = os.getenv(
        "OTEL_CONSOLE_EXPORTER", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}

    # Default points to <project_root>\logs\t2p_system.log
    LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "t2p_system.log"))

    # --- DeepSeek API configuration ---
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    if AI_MODE == "live" and not DEEPSEEK_API_KEY:
        logger.error("❌ DEEPSEEK_API_KEY not found in environment variables")

    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")

    # --- Dedicated multimodal OCR provider ---
    # DeepSeek V4 is used only for text reasoning/grading. Handwritten images
    # must be transcribed by a separate vision-capable, OpenAI-compatible API.
    VISION_PROVIDER = os.getenv("VISION_PROVIDER", "openai-compatible")
    VISION_API_KEY = os.getenv("VISION_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    VISION_BASE_URL = os.getenv("VISION_BASE_URL", "https://api.openai.com/v1")
    VISION_MODEL = os.getenv("VISION_MODEL", "")
    VISION_MAX_TOKENS = int(os.getenv("VISION_MAX_TOKENS", "4096"))

    # --- Model generation control parameters ---
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", 0.5))
    DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", 16384))
    DEFAULT_TOP_P = float(os.getenv("DEFAULT_TOP_P", 0.95))

    # --- Runtime scheduling configuration ---
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1))
    REQUEST_DELAY = int(os.getenv("REQUEST_DELAY", 30))

    # [Recommendation]: Considering 429 risk, retry count can be maintained at 3 or increased to 5
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    ENABLE_SEMANTIC_DEDUP = os.getenv(
        "ENABLE_SEMANTIC_DEDUP", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    SEMANTIC_MODEL = os.getenv(
        "SEMANTIC_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )

    # --- Log level ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def ensure_dirs(cls):
        """Ensure necessary directories exist"""
        Path(cls.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(cls.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)


# Auto-initialize directories
Config.ensure_dirs()
