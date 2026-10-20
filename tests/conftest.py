"""Tests never use real account data or external model endpoints."""
import os
import tempfile
from pathlib import Path

_test_root = Path(tempfile.mkdtemp(prefix="atelier-tests-"))
os.environ["AI_MODE"] = "simulation"
os.environ["ALLOW_PAID_API"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{(_test_root / 'test.db').as_posix()}"
os.environ["OUTPUT_DIR"] = str(_test_root / "output")
os.environ["RAG_ALLOW_DOWNLOAD"] = "false"

import pytest


@pytest.fixture(autouse=True)
def no_model_network(monkeypatch):
    from src.rag import get_retriever
    retriever = get_retriever()
    monkeypatch.setattr(retriever, "use_dense", False)
    monkeypatch.setattr(retriever, "dense_status", "disabled_for_unit_tests")
    import httpx
    original_send = httpx.Client.send

    def guarded_send(client, request, *args, **kwargs):
        if request.url.host not in {"testserver", "localhost", "127.0.0.1"}:
            raise AssertionError("External HTTP calls are forbidden in tests.")
        return original_send(client, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", guarded_send)
