import json

import pytest

from src.rag.ingestion import build_document, store_document, sections_from_content
from src.rag.service import RetrievalService


def document(path, version="1", publish=False):
    return build_document(path, source_id="test-notes", title="Test notes", version=version,
                          topic="Derivatives", provenance="Original test data", license_name="CC0-1.0", publish=publish)


def test_drafts_are_not_searchable_and_import_is_idempotent(tmp_path):
    source = tmp_path / "input.md"
    source.write_text("# Chain rule\nDifferentiate the outer function and multiply by the inner derivative.", encoding="utf-8")
    folder = tmp_path / "knowledge"
    doc = document(source)
    target = store_document(doc, folder)
    original = target.stat().st_mtime_ns
    assert store_document(doc, folder).stat().st_mtime_ns == original
    assert RetrievalService(knowledge_path=folder, use_dense=False).chunks == []
    store_document(document(source, publish=True), folder)
    assert len(RetrievalService(knowledge_path=folder, use_dense=False).chunks) == 1


def test_changed_content_requires_new_version_and_archives_original(tmp_path):
    source = tmp_path / "input.md"
    source.write_text("# Rule\nFirst text.", encoding="utf-8")
    folder = tmp_path / "knowledge"
    store_document(document(source, publish=True), folder)
    source.write_text("# Rule\nChanged text.", encoding="utf-8")
    with pytest.raises(ValueError, match="new version"):
        store_document(document(source, publish=True), folder)
    store_document(document(source, version="2", publish=True), folder)
    assert len(list((folder / "archive").glob("*.json"))) == 1


def test_import_does_not_cut_math_or_oversized_sections(tmp_path):
    source = tmp_path / "bad.md"
    source.write_text("# Rule\n$$ x^2", encoding="utf-8")
    with pytest.raises(ValueError, match="Unbalanced"):
        document(source)
    source.write_text("# Rule\n" + "x" * 1700, encoding="utf-8")
    with pytest.raises(ValueError, match="too long"):
        document(source)


def test_invalid_pdf_is_a_readable_import_error():
    with pytest.raises(ValueError, match="Unable to read this PDF"):
        sections_from_content(b"not a PDF file", "broken.pdf")
