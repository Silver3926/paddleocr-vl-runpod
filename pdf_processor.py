import os
import shutil
import logging
from pathlib import Path
from typing import Generator, Optional

import requests
import fitz  # PyMuPDF
from PIL import Image

from config import TEMP_DIR, MAX_PDF_PAGES


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def create_job_directory(job_id: str) -> Path:
    """
    Create an isolated temporary directory for one RunPod job.
    """
    job_dir = Path(TEMP_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    return job_dir


def cleanup_job_directory(job_dir: Path) -> None:
    """
    Remove all temporary files created for a job.
    """
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_file(
    url: str,
    destination: Path,
    timeout: int = 120,
) -> Path:
    """
    Download a remote file to local temporary storage.
    """

    logger.info("Downloading file: %s", url)

    response = requests.get(
        url,
        stream=True,
        timeout=timeout,
    )

    response.raise_for_status()

    with destination.open("wb") as file:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                file.write(chunk)

    logger.info(
        "Downloaded file: %s (%.2f MB)",
        destination,
        destination.stat().st_size / (1024 * 1024),
    )

    return destination


# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------

def validate_pdf(pdf_path: Path) -> int:
    """
    Open the PDF and return its page count.
    """

    logger.info("Opening PDF: %s", pdf_path)

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise ValueError(
            f"Unable to open PDF: {exc}"
        ) from exc

    try:
        page_count = document.page_count
    finally:
        document.close()

    if page_count == 0:
        raise ValueError("PDF contains no pages.")

    logger.info(
        "PDF contains %d pages",
        page_count,
    )

    return page_count


# ---------------------------------------------------------------------------
# PDF → images
# ---------------------------------------------------------------------------

def render_pdf_pages(
    pdf_path: Path,
    output_dir: Path,
    max_pages: Optional[int] = None,
    dpi: int = 150,
) -> Generator[Path, None, None]:
    """
    Render PDF pages into PNG images.

    Pages are rendered one at a time to avoid keeping
    the entire PDF in memory.
    """

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    document = fitz.open(pdf_path)

    try:
        total_pages = document.page_count

        if max_pages is None or max_pages <= 0:
            pages_to_process = total_pages
        else:
            pages_to_process = min(
                total_pages,
                max_pages,
            )

        logger.info(
            "Rendering %d/%d PDF pages at %d DPI",
            pages_to_process,
            total_pages,
            dpi,
        )

        zoom = dpi / 72.0

        matrix = fitz.Matrix(
            zoom,
            zoom,
        )

        for page_index in range(pages_to_process):
            page = document.load_page(page_index)

            pixmap = page.get_pixmap(
                matrix=matrix,
                alpha=False,
            )

            image_path = (
                output_dir /
                f"page_{page_index + 1:05d}.png"
            )

            pixmap.save(str(image_path))

            logger.debug(
                "Rendered page %d → %s",
                page_index + 1,
                image_path,
            )

            yield image_path

    finally:
        document.close()


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

def validate_image(image_path: Path) -> None:
    """
    Validate that a rendered image can be opened.
    """

    try:
        with Image.open(image_path) as image:
            image.verify()

    except Exception as exc:
        raise ValueError(
            f"Invalid image generated from PDF: "
            f"{image_path}"
        ) from exc


# ---------------------------------------------------------------------------
# High-level PDF iterator
# ---------------------------------------------------------------------------

def iter_pdf_images(
    pdf_path: Path,
    output_dir: Path,
    max_pages: Optional[int] = None,
    dpi: int = 150,
) -> Generator[tuple[int, Path], None, None]:
    """
    Yield:

        (page_number, image_path)

    one page at a time.
    """

    if max_pages is None:
        max_pages = MAX_PDF_PAGES

    for page_number, image_path in enumerate(
        render_pdf_pages(
            pdf_path=pdf_path,
            output_dir=output_dir,
            max_pages=max_pages,
            dpi=dpi,
        ),
        start=1,
    ):
        validate_image(image_path)

        yield page_number, image_path