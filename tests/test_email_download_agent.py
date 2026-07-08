from __future__ import annotations

import json
from pathlib import Path
import shutil
from uuid import uuid4

from app.extraction.email_download_agent import EmailDownloadExtractionAgent

TEST_WORK_DIR = Path(".test-work")


def _prepare_case_dir(name: str) -> Path:
    root = TEST_WORK_DIR / "email_download_agent" / f"{name}-{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_extract_file_forwards_docx_without_model():
    root = _prepare_case_dir("forward_docx")
    try:
        source_dir = root / "downloads"
        source_dir.mkdir()
        source_file = source_dir / "report.docx"
        source_file.write_bytes(b"docx-bytes")

        destination_dir = root / "raw_json"
        agent = EmailDownloadExtractionAgent(destination_dir=destination_dir)

        result = agent.extract_file(source_file)

        assert result.status == "forwarded"
        assert result.output_file is not None
        assert Path(result.output_file).read_bytes() == b"docx-bytes"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_extract_file_writes_extracted_json_when_model_payload_is_available():
    root = _prepare_case_dir("extract_pdf")
    try:
        source_dir = root / "downloads"
        source_dir.mkdir()
        source_file = source_dir / "ticket.pdf"
        source_file.write_bytes(b"%PDF-1.4")

        destination_dir = root / "raw_json"
        agent = EmailDownloadExtractionAgent(destination_dir=destination_dir)
        agent._has_model_extractor = lambda: True  # type: ignore[method-assign]
        agent._extract_structured_payload = lambda path: {  # type: ignore[method-assign]
            "page_1": {
                "document_type": "client_maintenance_form",
                "maintenance_details": {"client": "Pharmacie Victoria"},
            }
        }

        result = agent.extract_file(source_file)

        assert result.status == "extracted"
        assert result.output_file is not None
        payload = json.loads(Path(result.output_file).read_text(encoding="utf-8"))
        assert payload["page_1"]["maintenance_details"]["client"] == "Pharmacie Victoria"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_extract_file_marks_pdf_as_pending_when_no_api_key():
    root = _prepare_case_dir("pending_pdf")
    try:
        source_dir = root / "downloads"
        source_dir.mkdir()
        source_file = source_dir / "ticket.pdf"
        source_file.write_bytes(b"%PDF-1.4")

        destination_dir = root / "raw_json"
        agent = EmailDownloadExtractionAgent(destination_dir=destination_dir)
        agent._has_model_extractor = lambda: False  # type: ignore[method-assign]

        result = agent.extract_file(source_file)

        assert result.status == "pending_extraction"
        assert result.output_file is None
    finally:
        shutil.rmtree(root, ignore_errors=True)
