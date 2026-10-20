"""Prepare a local embedding model; no paid model requests."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Allow free model download (approximately 0.5 GB).")
    args = parser.parse_args()
    os.environ["AI_MODE"] = "simulation"
    os.environ["ALLOW_PAID_API"] = "false"
    from src.config import Config
    Config.RAG_ALLOW_DOWNLOAD = args.download
    from src.rag import get_retriever
    status = get_retriever().prepare()
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if status["dense_status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
