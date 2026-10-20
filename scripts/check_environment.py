"""Windows runtime diagnostics without credentials or paid API calls."""
import json
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from src.config import Config
    report = {"platform": platform.system(), "python": platform.python_version(),
              "python_executable": sys.executable, "node_found": bool(shutil.which("node")),
              "ai_mode": Config.AI_MODE, "paid_calls_enabled": Config.AI_MODE == "live" and Config.ALLOW_PAID_API,
              "model_cache": str(Config.RAG_CACHE_DIR),
              "free_disk_gb": round(shutil.disk_usage(Config.BASE_DIR).free / 2**30, 2)}
    try:
        import torch
        report.update(torch=torch.__version__, cuda_runtime=torch.version.cuda,
                      cuda_available=torch.cuda.is_available())
        if torch.cuda.is_available():
            torch.ones(1, device="cuda").sum().item()
            report["gpu"] = torch.cuda.get_device_name(0)
        else:
            report["device_note"] = "CPU fallback: CUDA unavailable. Install the CUDA wheel if compatible NVIDIA hardware is present."
    except Exception as error:
        report["device_note"] = f"CUDA check failed: {type(error).__name__}; model loader will try CPU."
    from src.rag import get_retriever
    report["retrieval"] = get_retriever().prepare()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
