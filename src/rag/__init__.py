"""Local, versioned course retrieval; no remote generation calls."""

from src.rag.service import get_retriever

__all__ = ["get_retriever"]
