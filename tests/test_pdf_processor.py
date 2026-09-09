from pathlib import Path

import pytest
from PIL import Image

from pdf_processor import (
    _safe_job_directory_name,
    create_job_directory,
    validate_input_file,
    validate_pdf_signature,
)


def test_job_id_is_hashed_and_safe(tmp_path, monkeypatch):
    monkeypatch.setattr("pdf_processor.TEMP_DIR", str(tmp_path))

    job_dir = create_job_directory("../../etc/passwd")

    assert job_dir.parent == tmp_path.resolve()
    assert job_dir.name == _safe_job_directory_name("../../etc/passwd")
    assert len(job_dir.name) == 32


def test_pdf_magic_bytes_are_required(tmp_path):
    path = tmp_path / "not-a-pdf.pdf"
    path.write_bytes(b"<html>not a pdf</html>")

    with pytest.raises(ValueError, match="PDF signature"):
        validate_pdf_signature(path)


def test_invalid_pdf_is_rejected_before_parser(tmp_path):
    path = tmp_path / "invalid.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(ValueError, match="PDF signature"):
        validate_input_file(path, "pdf")


def test_supported_image_is_accepted(tmp_path):
    path = tmp_path / "image.bin"
    Image.new("RGB", (2, 2), "white").save(path, format="PNG")

    assert validate_input_file(path, "image") is None


def test_unsupported_image_is_rejected(tmp_path):
    path = tmp_path / "image.gif"
    Image.new("RGB", (2, 2), "white").save(path, format="GIF")

    with pytest.raises(ValueError, match="Unsupported image format"):
        validate_input_file(path, "image")
