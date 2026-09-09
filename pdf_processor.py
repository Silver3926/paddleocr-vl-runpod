import hashlib
import logging
import shutil
from pathlib import Path
from urllib.parse import urljoin

import fitz
import requests
from PIL import Image

from config import (
    DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
    DOWNLOAD_READ_TIMEOUT_SECONDS,
    MAX_DOWNLOAD_SIZE_MB,
    MAX_PDF_PAGES,
    TEMP_DIR,
)
from url_security import validate_remote_url

logger = logging.getLogger(__name__)
MAX_REDIRECTS = 5
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF", "BMP"}


def _safe_job_directory_name(job_id: str) -> str:
    return hashlib.sha256(str(job_id).encode("utf-8")).hexdigest()[:32]


def create_job_directory(job_id: str) -> Path:
    root = Path(TEMP_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    job_dir = root / _safe_job_directory_name(job_id)
    job_dir.mkdir(parents=False, exist_ok=False)
    if job_dir.parent != root:
        raise RuntimeError("Invalid job directory path.")
    return job_dir


def cleanup_job_directory(job_dir: Path) -> None:
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)


def validate_url(url: str) -> str:
    return validate_remote_url(url)


def _check_content_length(response: requests.Response, limit: int) -> None:
    header = response.headers.get("Content-Length")
    if not header:
        return
    try:
        size = int(header)
    except ValueError:
        return
    if size > limit:
        raise ValueError(
            f"Downloaded file exceeds MAX_DOWNLOAD_SIZE_MB={MAX_DOWNLOAD_SIZE_MB} MB."
        )


def download_file(
    url: str,
    destination: Path,
    timeout: tuple[int, int] | None = None,
) -> Path:
    current_url = validate_remote_url(url)
    max_size = MAX_DOWNLOAD_SIZE_MB * 1024 * 1024
    request_timeout = timeout or (
        DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
        DOWNLOAD_READ_TIMEOUT_SECONDS,
    )

    try:
        with requests.Session() as session:
            for redirect_count in range(MAX_REDIRECTS + 1):
                response = session.get(
                    current_url,
                    stream=True,
                    timeout=request_timeout,
                    allow_redirects=False,
                )

                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        raise ValueError("Remote server returned an invalid redirect.")
                    if redirect_count >= MAX_REDIRECTS:
                        raise ValueError("Too many redirects while downloading file.")
                    current_url = validate_remote_url(
                        urljoin(current_url, location)
                    )
                    continue

                response.raise_for_status()
                _check_content_length(response, max_size)
                try:
                    with response, destination.open("wb") as output:
                        downloaded = 0
                        for chunk in response.iter_content(1024 * 1024):
                            if not chunk:
                                continue
                            downloaded += len(chunk)
                            if downloaded > max_size:
                                raise ValueError(
                                    "Downloaded file exceeds "
                                    f"MAX_DOWNLOAD_SIZE_MB={MAX_DOWNLOAD_SIZE_MB} MB."
                                )
                            output.write(chunk)
                except Exception:
                    destination.unlink(missing_ok=True)
                    raise
                break
            else:
                raise ValueError("Unable to download file after redirects.")
    except requests.RequestException as exc:
        raise RuntimeError("Unable to download remote file.") from exc

    if not destination.exists() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("Downloaded file is empty.")
    return destination


def validate_pdf_signature(pdf_path: Path) -> None:
    with pdf_path.open("rb") as file:
        if file.read(5) != b"%PDF-":
            raise ValueError("File does not have a valid PDF signature.")


def validate_pdf(pdf_path: Path) -> int:
    validate_pdf_signature(pdf_path)
    try:
        document = fitz.open(str(pdf_path))
    except Exception as exc:
        raise ValueError("Unable to open PDF.") from exc
    try:
        page_count = document.page_count
    finally:
        document.close()
    if page_count <= 0:
        raise ValueError("PDF contains no pages.")
    if page_count > MAX_PDF_PAGES:
        raise ValueError(
            f"PDF contains too many pages (maximum: {MAX_PDF_PAGES})."
        )
    return page_count


def validate_image(image_path: Path) -> None:
    Image.MAX_IMAGE_PIXELS = 50_000_000
    try:
        with Image.open(image_path) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError(f"Unsupported image format: {image.format}.")
            image.verify()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Invalid image file.") from exc


def validate_input_file(file_path: Path, file_type: str) -> int | None:
    if not file_path.exists():
        raise FileNotFoundError("Input file does not exist.")
    if file_path.stat().st_size == 0:
        raise ValueError("Input file is empty.")
    if file_type == "pdf":
        return validate_pdf(file_path)
    if file_type == "image":
        validate_image(file_path)
        return None
    raise ValueError("Unsupported input file type.")
