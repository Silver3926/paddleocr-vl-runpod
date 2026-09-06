import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse

import fitz  # PyMuPDF
import requests
from PIL import Image

from config import (
    MAX_DOWNLOAD_SIZE_MB,
    MAX_PDF_PAGES,
    TEMP_DIR,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Temporary directory
# ---------------------------------------------------------------------------

def create_job_directory(
    job_id: str,
) -> Path:
    """
    Create an isolated temporary directory for one RunPod job.
    """

    job_dir = (
        Path(TEMP_DIR) /
        job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    return job_dir


def cleanup_job_directory(
    job_dir: Path,
) -> None:
    """
    Remove all temporary files created for a job.
    """

    if job_dir.exists():

        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def validate_url(
    url: str,
) -> str:
    """
    Validate and normalize an HTTP/HTTPS URL.
    """

    if not isinstance(
        url,
        str,
    ):

        raise ValueError(
            "Input URL must be a string."
        )

    url = url.strip()

    if not url:

        raise ValueError(
            "Input URL must be a non-empty string."
        )

    try:

        parsed = urlparse(
            url
        )

    except Exception as exc:

        raise ValueError(
            f"Invalid input URL: {exc}"
        ) from exc

    if parsed.scheme not in {
        "http",
        "https",
    }:

        raise ValueError(
            "Input URL must use HTTP or HTTPS."
        )

    if not parsed.netloc:

        raise ValueError(
            "Input URL must contain a valid host."
        )

    return url


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

    The download is streamed and limited by MAX_DOWNLOAD_SIZE_MB.
    """

    url = validate_url(
        url
    )

    # ---------------------------------------------------------------
    # Maximum download size
    # ---------------------------------------------------------------

    max_size_bytes = (
        MAX_DOWNLOAD_SIZE_MB
        * 1024
        * 1024
    )

    logger.info(
        "Downloading file: %s",
        url,
    )

    # ---------------------------------------------------------------
    # HTTP request
    # ---------------------------------------------------------------

    try:

        with requests.Session() as session:

            response = session.get(
                url,
                stream=True,
                timeout=timeout,
                allow_redirects=True,
            )

            response.raise_for_status()

            # -------------------------------------------------------
            # Content-Length check
            # -------------------------------------------------------

            content_length = response.headers.get(
                "Content-Length"
            )

            if content_length:

                try:

                    content_length = int(
                        content_length
                    )

                except ValueError:

                    content_length = None

                if (
                    content_length is not None
                    and content_length > max_size_bytes
                ):

                    raise ValueError(
                        "Downloaded file exceeds "
                        f"MAX_DOWNLOAD_SIZE_MB="
                        f"{MAX_DOWNLOAD_SIZE_MB} MB."
                    )

            # -------------------------------------------------------
            # Stream response to disk
            # -------------------------------------------------------

            downloaded_bytes = 0

            try:

                with destination.open(
                    "wb"
                ) as file:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024,
                    ):

                        if not chunk:
                            continue

                        downloaded_bytes += len(
                            chunk
                        )

                        if (
                            downloaded_bytes
                            > max_size_bytes
                        ):

                            raise ValueError(
                                "Downloaded file exceeds "
                                f"MAX_DOWNLOAD_SIZE_MB="
                                f"{MAX_DOWNLOAD_SIZE_MB} MB."
                            )

                        file.write(
                            chunk
                        )

            except Exception:

                # Remove incomplete download.
                if destination.exists():

                    destination.unlink(
                        missing_ok=True
                    )

                raise

    except requests.RequestException as exc:

        raise RuntimeError(
            f"Unable to download file: {exc}"
        ) from exc

    # ---------------------------------------------------------------
    # Final file check
    # ---------------------------------------------------------------

    if not destination.exists():

        raise RuntimeError(
            "Downloaded file was not created."
        )

    if destination.stat().st_size == 0:

        destination.unlink(
            missing_ok=True
        )

        raise ValueError(
            "Downloaded file is empty."
        )

    logger.info(
        "Downloaded file: %s (%.2f MB)",
        destination,
        downloaded_bytes
        / (1024 * 1024),
    )

    return destination


# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------

def validate_pdf(
    pdf_path: Path,
) -> int:
    """
    Validate a PDF and return its page count.

    The PDF is rejected when it exceeds MAX_PDF_PAGES.
    """

    logger.info(
        "Validating PDF: %s",
        pdf_path,
    )

    try:

        document = fitz.open(
            str(pdf_path)
        )

    except Exception as exc:

        raise ValueError(
            f"Unable to open PDF: {exc}"
        ) from exc

    try:

        page_count = document.page_count

    finally:

        document.close()

    if page_count <= 0:

        raise ValueError(
            "PDF contains no pages."
        )

    logger.info(
        "PDF contains %d page(s).",
        page_count,
    )

    # ---------------------------------------------------------------
    # Maximum page limit
    # ---------------------------------------------------------------

    if page_count > MAX_PDF_PAGES:

        raise ValueError(
            f"PDF contains {page_count} pages, "
            f"but MAX_PDF_PAGES is "
            f"{MAX_PDF_PAGES}."
        )

    return page_count


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

def validate_image(
    image_path: Path,
) -> None:
    """
    Validate that an image can be opened.
    """

    logger.info(
        "Validating image: %s",
        image_path,
    )

    try:

        with Image.open(
            image_path
        ) as image:

            image.verify()

    except Exception as exc:

        raise ValueError(
            f"Invalid image file: "
            f"{image_path}"
        ) from exc

    logger.info(
        "Image validation successful."
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_input_file(
    file_path: Path,
    file_type: str,
) -> int | None:
    """
    Validate a downloaded input file.

    Returns:

        PDF:
            Number of pages.

        Image:
            None.
    """

    # ---------------------------------------------------------------
    # Existence
    # ---------------------------------------------------------------

    if not file_path.exists():

        raise FileNotFoundError(
            f"Input file does not exist: "
            f"{file_path}"
        )

    # ---------------------------------------------------------------
    # File size
    # ---------------------------------------------------------------

    file_size = file_path.stat().st_size

    if file_size == 0:

        raise ValueError(
            "Input file is empty."
        )

    logger.info(
        "Input file size: %.2f MB",
        file_size / (1024 * 1024),
    )

    # ---------------------------------------------------------------
    # File type
    # ---------------------------------------------------------------

    if file_type == "pdf":

        return validate_pdf(
            file_path
        )

    if file_type == "image":

        validate_image(
            file_path
        )

        return None

    raise ValueError(
        f"Unsupported file type: "
        f"{file_type}"
    )
