"""
Configuration file - Manages project paths, Vertex AI parameters, and generation control
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
    # Path(__file__).resolve() -> D:\PycharmBase\T2P\src\config.py
    # .parent.parent -> D:\PycharmBase\T2P
    BASE_DIR = Path(__file__).resolve().parent.parent
    BASE_DIR = Path(__file__).resolve().parent.parent
    print(f"Currently identified project root directory: {BASE_DIR}")  # Check console output after running

    # --- Resource paths ---
    # Default points to D:\PycharmBase\T2P\data\golden_dataset_v2.json
    GOLDEN_DATASET_PATH = os.getenv("GOLDEN_DATASET_PATH", str(BASE_DIR / "data" / "golden_dataset_v3.json"))

    # Default points to D:\PycharmBase\T2P\output
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "output"))

    # Default points to D:\PycharmBase\T2P\logs\t2p_system.log
    LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "t2p_system.log"))

    # --- Vertex AI core configuration ---
    # Modified (more secure)
    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT_ID:
        logger.error("❌ GOOGLE_CLOUD_PROJECT not found in environment variables")

    # [Modification]: Changed default region from europe-west1 to us-central1
    LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    # Added this line to ensure the program can read your API Key[cite: 8, 11]
    API_KEY = os.getenv("GOOGLE_API_KEY")
    # Keep using gemini-2.5-pro
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

    # --- Model generation control parameters ---
    DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", 0.5))
    DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", 16384))
    DEFAULT_TOP_P = float(os.getenv("DEFAULT_TOP_P", 0.95))
    DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", 40))

    # --- Runtime scheduling configuration ---
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1))
    REQUEST_DELAY = int(os.getenv("REQUEST_DELAY", 30))

    # [Recommendation]: Considering 429 risk, retry count can be maintained at 3 or increased to 5
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

    # --- Log level ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def ensure_dirs(cls):
        """Ensure necessary directories exist"""
        Path(cls.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(cls.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)


# Auto-initialize directories
Config.ensure_dirs()