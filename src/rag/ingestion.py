"""Local administrator import. Publishing is explicit; formula blocks stay intact."""
import json
import os
import re
import tempfile
import io
from pathlib import Path

from src.rag.service import digest


def read_sections(path):
    path = Path(path)
    return sections_from_content(path.read_bytes(), path.name)


def sections_from_content(content, filename):
    path = Path(filename)
    if len(content) > 5_000_000:
        raise ValueError("Course files must be 5 MB or smaller.")
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise ValueError("PDF import requires pypdf. Install requirements.txt first.") from error
        from pypdf.errors import PdfReadError
        try:
            reader = PdfReader(io.BytesIO(content))
            if len(reader.pages) > 50:
                raise ValueError("Import at most 50 PDF pages at a time.")
            sections = [(f"Page {index + 1}", page.extract_text() or "")
                        for index, page in enumerate(reader.pages)]
        except (PdfReadError, NotImplementedError) as error:
            raise ValueError("Unable to read this PDF. Use an unencrypted, valid text PDF.") from error
        if not any(text.strip() for _, text in sections):
            raise ValueError("This PDF has no extractable text; OCR and formula review are required.")
        return sections
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Use Markdown, text, PDF, or a structured JSON manifest.")
    text = content.decode("utf-8-sig")
    parts = re.split(r"(?m)^#{1,4}\s+(.+)\n", text)
    sections = [(path.stem, parts[0])] if parts[0].strip() else []
    sections.extend((parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2))
    return sections


def build_document(path, *, source_id, title, version, topic, provenance, license_name, publish=False):
    path = Path(path)
    return build_document_from_content(path.read_bytes(), filename=path.name, source_id=source_id,
        title=title, version=version, topic=topic, provenance=provenance, license_name=license_name, publish=publish)


def build_document_from_content(content, *, filename, source_id, title, version, topic, provenance, license_name, publish=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
        raise ValueError("Source ID must contain only letters, digits, underscores or hyphens.")
    if not all(str(value).strip() for value in (title, version, topic, provenance, license_name)):
        raise ValueError("Title, version, topic, provenance and license are required.")
    path = Path(filename)
    if len(content) > 5_000_000:
        raise ValueError("Course files must be 5 MB or smaller.")
    if path.suffix.lower() == ".json":
        document = json.loads(content.decode("utf-8-sig"))
        if not isinstance(document, dict) or not isinstance(document.get("chunks"), list):
            raise ValueError("A JSON manifest needs a chunks array.")
    else:
        chunks = []
        for index, (heading, text) in enumerate(sections_from_content(content, filename), start=1):
            text = text.strip()
            if not text:
                continue
            # Reject oversized semantic units instead of silently cutting a theorem or formula.
            if len(text) > 1600:
                raise ValueError(f"Section {heading!r} is too long. Split it into reviewed subsections before import.")
            if text.count("$$") % 2:
                raise ValueError(f"Unbalanced display math in {heading!r}.")
            chunks.append({"id": f"{source_id}-{index}", "topic": topic, "title": heading,
                           "section": str(index), "text": text, "concepts": [],
                           "resource_type": "course_note", "prerequisites": []})
        document = {"chunks": chunks}
    document.update(source_id=source_id, title=title, version=version, provenance=provenance,
                    license=license_name, status="published" if publish else "draft")
    if not document["chunks"]:
        raise ValueError("No knowledge units were imported.")
    for chunk in document["chunks"]:
        if not isinstance(chunk, dict):
            raise ValueError("Every knowledge unit must be an object.")
        if not all(chunk.get(k) for k in ("id", "topic", "title", "section", "text")):
            raise ValueError("Every chunk requires id, topic, title, section and text.")
        if not all(isinstance(chunk[k], str) for k in ("id", "topic", "title", "section", "text")):
            raise ValueError("Knowledge identifiers, metadata and text must be strings.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", str(chunk["id"])):
            raise ValueError("Knowledge unit IDs must contain only letters, digits, underscores or hyphens.")
        if not isinstance(chunk["text"], str) or len(chunk["text"]) > 1600 or chunk["text"].count("$$") % 2:
            raise ValueError("Knowledge text must be at most 1600 characters with balanced display math.")
        if not isinstance(chunk.get("concepts", []), list) or any(not isinstance(c, str) for c in chunk.get("concepts", [])):
            raise ValueError("Concept labels must be a list of strings.")
    if len(document["chunks"]) > 100 or len({c["id"] for c in document["chunks"]}) != len(document["chunks"]):
        raise ValueError("Use at most 100 units, each with a unique ID.")
    return document


def store_document(document, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{document['source_id']}.json"
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if digest(previous) == digest(document):
            return target
        if previous.get("version") == document.get("version") and previous.get("chunks") != document.get("chunks"):
            raise ValueError("Changed source content requires a new version.")
        archive = directory / "archive"
        archive.mkdir(exist_ok=True)
        (archive / f"{document['source_id']}-{digest(previous)[:16]}.json").write_text(
            json.dumps(previous, indent=2, ensure_ascii=False), encoding="utf-8")
    fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
