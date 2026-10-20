"""Trusted local course administration; no upload endpoint or remote URL fetching."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from src.config import Config
    from src.rag.ingestion import build_document, store_document
    from src.rag.service import RetrievalService
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    command = sub.add_parser("import")
    for name in ("file", "source-id", "title", "version", "topic", "provenance", "license"):
        command.add_argument("--" + name, required=True)
    command.add_argument("--publish", action="store_true", help="Confirm that source rights, formulas and content have been reviewed.")
    args = parser.parse_args()
    if args.action == "import":
        document = build_document(args.file, source_id=args.source_id, title=args.title, version=args.version,
                                  topic=args.topic, provenance=args.provenance, license_name=args.license, publish=args.publish)
        print(store_document(document, Config.KNOWLEDGE_PATH))
    else:
        retriever = RetrievalService(use_dense=False)
        print(json.dumps({"sources": retriever.sources, "status": retriever.status()}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
