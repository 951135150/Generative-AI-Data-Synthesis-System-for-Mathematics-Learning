"""Course catalog and authenticated administrator publishing operations."""
import base64
import json
import re
import threading
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from src.auth_dependencies import current_identity
from src.auth import AuthIdentity
from src.config import Config
from src.rag import get_retriever
from src.rag.ingestion import build_document_from_content, store_document
from src.rag.service import digest

router = APIRouter(prefix="/knowledge", tags=["Course knowledge"])
_catalog_lock = threading.RLock()


def administrator(identity: AuthIdentity = Depends(current_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail={"code": "ADMIN_REQUIRED", "message": "Course publishing requires an administrator account."})
    return identity


class SourceImport(BaseModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=60)
    topic: str = Field(min_length=1, max_length=200)
    provenance: str = Field(min_length=1, max_length=1000)
    license_name: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=7_000_000)
    encoding: Literal["text", "base64"] = "text"
    publish: bool = False
    review_confirmed: bool = False
    expected_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def checked_publication(self):
        if self.publish and not self.review_confirmed:
            raise ValueError("Confirm review of source rights, formulas and content before publishing.")
        return self


class SourceState(BaseModel):
    status: Literal["published", "withdrawn"]
    expected_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_confirmed: bool = False


def source_path(source_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
        raise HTTPException(status_code=422, detail="Invalid source identifier.")
    return Path(Config.KNOWLEDGE_PATH) / f"{source_id}.json"


def read_source(source_id):
    path = source_path(source_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Course source not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def assert_current(source_id, expected_hash):
    path = source_path(source_id)
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if digest(current) != expected_hash:
            raise HTTPException(status_code=409, detail={"code": "SOURCE_CHANGED", "message": "The source changed. Refresh the catalog and preview again."})
    elif expected_hash is not None:
        raise HTTPException(status_code=409, detail="The original source is no longer present.")


def build_import(payload):
    raw = (base64.b64decode(payload.content, validate=True) if payload.encoding == "base64"
           else payload.content.encode("utf-8"))
    return build_document_from_content(raw, filename=payload.filename, source_id=payload.source_id,
        title=payload.title, version=payload.version, topic=payload.topic,
        provenance=payload.provenance, license_name=payload.license_name, publish=payload.publish)


def check_collision(document):
    incoming = {c["id"] for c in document["chunks"]}
    for path in Path(Config.KNOWLEDGE_PATH).glob("*.json"):
        other = json.loads(path.read_text(encoding="utf-8"))
        if other.get("source_id") != document["source_id"] and incoming.intersection(c["id"] for c in other.get("chunks", [])):
            raise ValueError("Knowledge unit IDs overlap another source; use source-specific IDs.")


def check_publish(document):
    check_collision(document)
    try:
        return get_retriever().validate_document(document)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail={"code": "LOCAL_MODEL_REQUIRED", "message": str(error)}) from error


@router.get("/catalog")
def catalog():
    retriever = get_retriever()
    retriever.refresh()
    # Worked examples stay outside the general source browser to reduce exam leakage.
    chunks = [c for c in retriever.chunks if c.get("resource_type") != "worked_example"]
    return {"success": True, "sources": retriever.sources, "chunks": chunks, "retrieval": retriever.status()}


@router.get("/search")
def search(query: str = Query(min_length=1, max_length=500), topic: str | None = Query(default=None, max_length=200)):
    bundle = get_retriever().retrieve(query, topics=[topic] if topic else None,
                                      purpose="course_lookup", top_k=5, exam=True)
    return {"success": True, "data": bundle}


@router.get("/manage/sources")
def managed_sources(_identity=Depends(administrator)):
    sources = []
    with _catalog_lock:
        for path in sorted(Path(Config.KNOWLEDGE_PATH).glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            sources.append({**{k: doc.get(k) for k in ("source_id", "title", "version", "status", "provenance", "license")},
                            "chunk_count": len(doc.get("chunks", [])), "source_hash": digest(doc)})
    return {"success": True, "sources": sources}


@router.post("/manage/preview")
def preview(payload: SourceImport, _identity=Depends(administrator)):
    try:
        document = build_import(payload)
        checks = check_publish(document) if payload.publish else {"tokenizer_checked": False}
        existing = source_path(payload.source_id)
        return {"success": True, "document": document, "checks": checks,
                "existing_hash": digest(json.loads(existing.read_text(encoding="utf-8"))) if existing.exists() else None,
                "preview_hash": digest(document)}
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail={"code": "INVALID_COURSE_SOURCE", "message": str(error)}) from error


@router.get("/manage/sources/{source_id}")
def managed_source(source_id: str, _identity=Depends(administrator)):
    with _catalog_lock:
        document = read_source(source_id)
    return {"success": True, "document": document, "source_hash": digest(document)}


@router.post("/manage/save")
def save(payload: SourceImport, _identity=Depends(administrator)):
    try:
        with _catalog_lock:
            assert_current(payload.source_id, payload.expected_hash)
            document = build_import(payload)
            if payload.publish:
                check_publish(document)
            else:
                check_collision(document)
            store_document(document, Config.KNOWLEDGE_PATH)
            get_retriever().refresh()
        return {"success": True, "source_id": payload.source_id, "status": document["status"], "source_hash": digest(document)}
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail={"code": "INVALID_COURSE_SOURCE", "message": str(error)}) from error


@router.post("/manage/sources/{source_id}/status")
def source_state(source_id: str, payload: SourceState, _identity=Depends(administrator)):
    try:
        with _catalog_lock:
            assert_current(source_id, payload.expected_hash)
            document = read_source(source_id)
            if payload.status == "published":
                if not payload.review_confirmed:
                    raise HTTPException(status_code=422, detail="Confirm rights and content review before publishing.")
                check_publish(document)
            document["status"] = payload.status
            store_document(document, Config.KNOWLEDGE_PATH)
            get_retriever().refresh()
        return {"success": True, "status": payload.status, "source_hash": digest(document)}
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail={"code": "INVALID_COURSE_SOURCE", "message": str(error)}) from error
