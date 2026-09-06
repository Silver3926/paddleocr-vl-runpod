import logging
import uuid
from pathlib import Path
from typing import Any

import runpod
from paddleocr import PaddleOCRVL

from config import (
    CONCATENATE_PAGES,
    DEVICE,
    LOG_LEVEL,
    MERGE_TABLES,
    PIPELINE_VERSION,
    RELEVEL_TITLES,
    RETURN_JSON,
    TEMP_DIR,
)
from pdf_processor import (
    cleanup_job_directory,
    create_job_directory,
    download_file,
    validate_input_file,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(
        logging,
        LOG_LEVEL.upper(),
        logging.INFO,
    ),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PaddleOCR-VL initialization
# ---------------------------------------------------------------------------

logger.info(
    "=========================================="
)

logger.info(
    "Initializing PaddleOCR-VL..."
)

logger.info(
    "Pipeline version: %s",
    PIPELINE_VERSION,
)

logger.info(
    "Device: %s",
    DEVICE,
)

pipeline_kwargs = {
    "pipeline_version": PIPELINE_VERSION,
    "device": DEVICE,
}

logger.info(
    "PaddleOCR-VL configuration: %s",
    pipeline_kwargs,
)

try:
    pipeline = PaddleOCRVL(
        **pipeline_kwargs,
    )

except Exception as exc:
    logger.exception(
        "Failed to initialize PaddleOCR-VL."
    )

    raise RuntimeError(
        "PaddleOCR-VL initialization failed. "
        "Check PaddlePaddle, CUDA/GPU, model downloads, "
        "and PaddleOCR dependencies."
    ) from exc

logger.info(
    "PaddleOCR-VL pipeline initialized successfully."
)

logger.info(
    "=========================================="
)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def get_result_markdown(
    result: Any,
) -> str:
    """
    Extract Markdown text from a PaddleOCR-VL result.

    PaddleOCR-VL normally exposes result.markdown as a dictionary
    containing markdown_texts and related metadata.

    This function also supports simpler/string-based result formats
    for compatibility.
    """

    markdown = getattr(
        result,
        "markdown",
        None,
    )

    # ---------------------------------------------------------------
    # Markdown dictionary
    # ---------------------------------------------------------------

    if isinstance(
        markdown,
        dict,
    ):

        text = markdown.get(
            "markdown_texts"
        )

        if isinstance(
            text,
            str,
        ):
            return text

        if isinstance(
            text,
            list,
        ):
            return "\n\n".join(
                str(item)
                for item in text
                if item
            )

        text = markdown.get(
            "text"
        )

        if isinstance(
            text,
            str,
        ):
            return text

    # ---------------------------------------------------------------
    # Markdown string
    # ---------------------------------------------------------------

    if isinstance(
        markdown,
        str,
    ):
        return markdown

    # ---------------------------------------------------------------
    # Dictionary-like result fallback
    # ---------------------------------------------------------------

    if isinstance(
        result,
        dict,
    ):

        markdown = result.get(
            "markdown"
        )

        if isinstance(
            markdown,
            dict,
        ):

            text = markdown.get(
                "markdown_texts"
            )

            if isinstance(
                text,
                str,
            ):
                return text

            if isinstance(
                text,
                list,
            ):
                return "\n\n".join(
                    str(item)
                    for item in text
                    if item
                )

            text = markdown.get(
                "text"
            )

            if isinstance(
                text,
                str,
            ):
                return text

        if isinstance(
            markdown,
            str,
        ):
            return markdown

    return ""


def get_result_json(
    result: Any,
) -> Any:
    """
    Extract the structured JSON-compatible result.

    PaddleOCR/PaddleX result objects normally expose a `json`
    attribute containing structured result data.
    """

    value = getattr(
        result,
        "json",
        None,
    )

    # ---------------------------------------------------------------
    # Some implementations expose json as a callable.
    # ---------------------------------------------------------------

    if callable(value):

        try:
            value = value()

        except Exception as exc:

            logger.warning(
                "Unable to call result.json(): %s",
                exc,
            )

            value = None

    if value is not None:
        return value

    # ---------------------------------------------------------------
    # Dictionary fallback.
    # ---------------------------------------------------------------

    if isinstance(
        result,
        dict,
    ):
        return result

    # ---------------------------------------------------------------
    # Last-resort string representation.
    # ---------------------------------------------------------------

    try:
        return str(result)

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Result processing
# ---------------------------------------------------------------------------

def process_results(
    results: list[Any],
) -> tuple[str, list[Any]]:
    """
    Convert PaddleOCR-VL results into combined Markdown and JSON.

    Markdown from multiple result objects is combined into one document.

    JSON output contains one structured result per PaddleOCR-VL result.
    """

    markdown_parts: list[str] = []
    json_results: list[Any] = []

    for index, result in enumerate(
        results,
        start=1,
    ):

        markdown = get_result_markdown(
            result
        )

        if markdown:

            markdown_parts.append(
                f"<!-- Result {index} -->\n\n"
                f"{markdown}"
            )

        if RETURN_JSON:

            json_results.append(
                {
                    "result": get_result_json(
                        result
                    ),
                }
            )

    combined_markdown = "\n\n".join(
        markdown_parts
    )

    return (
        combined_markdown,
        json_results,
    )


# ---------------------------------------------------------------------------
# PDF processing
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: Path,
) -> tuple[str, list[Any], int]:
    """
    Process a PDF directly through PaddleOCR-VL.

    Returns:

        markdown
        structured results
        original PDF page count
    """

    logger.info(
        "Validating PDF..."
    )

    page_count = validate_input_file(
        file_path=pdf_path,
        file_type="pdf",
    )

    if page_count is None:
        raise ValueError(
            "Unable to determine PDF page count."
        )

    logger.info(
        "Original PDF page count: %d",
        page_count,
    )

    logger.info(
        "Processing PDF with PaddleOCR-VL: %s",
        pdf_path,
    )

    output = pipeline.predict(
        input=str(pdf_path),
    )

    # PaddleOCR returns a lazy iterator.
    pages = list(
        output
    )

    if not pages:

        raise ValueError(
            "PaddleOCR-VL returned no results."
        )

    logger.info(
        "PaddleOCR-VL returned %d page result(s).",
        len(pages),
    )

    # ---------------------------------------------------------------
    # Multi-page restructuring
    # ---------------------------------------------------------------

    processed_results = pages
    restructured = False

    if len(pages) > 1:

        try:

            logger.info(
                "Restructuring multi-page results..."
            )

            logger.info(
                "merge_tables=%s",
                MERGE_TABLES,
            )

            logger.info(
                "relevel_titles=%s",
                RELEVEL_TITLES,
            )

            logger.info(
                "concatenate_pages=%s",
                CONCATENATE_PAGES,
            )

            restructured_output = (
                pipeline.restructure_pages(
                    pages,
                    merge_tables=MERGE_TABLES,
                    relevel_titles=RELEVEL_TITLES,
                    concatenate_pages=CONCATENATE_PAGES,
                )
            )

            processed_results = list(
                restructured_output
            )

            if processed_results:

                restructured = True

                logger.info(
                    "Multi-page restructuring completed."
                )

                logger.info(
                    "Restructured result count: %d",
                    len(processed_results),
                )

            else:

                logger.warning(
                    "Restructuring returned no results. "
                    "Using original page results."
                )

                processed_results = pages

        except Exception as exc:

            logger.warning(
                "Multi-page restructuring failed: %s",
                exc,
            )

            logger.warning(
                "Falling back to original page results."
            )

            processed_results = pages

    # ---------------------------------------------------------------
    # Build output
    # ---------------------------------------------------------------

    markdown, results = process_results(
        processed_results
    )

    if not markdown:

        logger.warning(
            "PaddleOCR-VL produced no Markdown text."
        )

    if restructured:

        logger.info(
            "Output generated from restructured results."
        )

    else:

        logger.info(
            "Output generated from individual page results."
        )

    return (
        markdown,
        results,
        page_count,
    )


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

def process_image(
    image_path: Path,
) -> tuple[str, list[Any]]:
    """
    Process a single image through PaddleOCR-VL.
    """

    logger.info(
        "Validating image..."
    )

    validate_input_file(
        file_path=image_path,
        file_type="image",
    )

    logger.info(
        "Processing image: %s",
        image_path,
    )

    output = pipeline.predict(
        input=str(image_path),
    )

    results = list(
        output
    )

    if not results:

        raise ValueError(
            "PaddleOCR-VL returned no results."
        )

    markdown, json_results = process_results(
        results
    )

    if not markdown:

        logger.warning(
            "PaddleOCR-VL produced no Markdown text."
        )

    return (
        markdown,
        json_results,
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_url_input(
    value: Any,
    field_name: str,
) -> str:
    """
    Validate a URL input received from RunPod.
    """

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            f"'{field_name}' must be a string."
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"'{field_name}' must not be empty."
        )

    if not (
        value.startswith("https://")
        or value.startswith("http://")
    ):
        raise ValueError(
            f"'{field_name}' must use HTTP or HTTPS."
        )

    return value


# ---------------------------------------------------------------------------
# RunPod handler
# ---------------------------------------------------------------------------

def handler(
    job: dict[str, Any],
) -> dict[str, Any]:
    """
    RunPod Serverless handler.

    Supported inputs:

        {
            "input": {
                "image_url": "https://..."
            }
        }

    or:

        {
            "input": {
                "pdf_url": "https://..."
            }
        }
    """

    # ---------------------------------------------------------------
    # Validate job object
    # ---------------------------------------------------------------

    if not isinstance(
        job,
        dict,
    ):

        return {
            "success": False,
            "error": "RunPod job must be an object.",
        }

    job_id = job.get(
        "id",
        str(uuid.uuid4()),
    )

    job_input = job.get(
        "input",
        {},
    )

    logger.info(
        "Received RunPod job: %s",
        job_id,
    )

    # ---------------------------------------------------------------
    # Validate input object
    # ---------------------------------------------------------------

    if not isinstance(
        job_input,
        dict,
    ):

        return {
            "success": False,
            "error": "input must be an object.",
        }

    image_url = job_input.get(
        "image_url"
    )

    pdf_url = job_input.get(
        "pdf_url"
    )

    # ---------------------------------------------------------------
    # Require exactly one input
    # ---------------------------------------------------------------

    if not image_url and not pdf_url:

        return {
            "success": False,
            "error": (
                "Provide either 'image_url' "
                "or 'pdf_url'."
            ),
        }

    if image_url and pdf_url:

        return {
            "success": False,
            "error": (
                "Provide only one of "
                "'image_url' or 'pdf_url'."
            ),
        }

    # ---------------------------------------------------------------
    # Validate selected URL
    # ---------------------------------------------------------------

    if image_url:

        try:
            image_url = validate_url_input(
                image_url,
                "image_url",
            )

        except ValueError as exc:

            return {
                "success": False,
                "error": str(exc),
            }

    if pdf_url:

        try:
            pdf_url = validate_url_input(
                pdf_url,
                "pdf_url",
            )

        except ValueError as exc:

            return {
                "success": False,
                "error": str(exc),
            }

    # ---------------------------------------------------------------
    # Create isolated job directory
    # ---------------------------------------------------------------

    job_dir = create_job_directory(
        job_id
    )

    logger.info(
        "Job directory: %s",
        job_dir,
    )

    try:

        # ===========================================================
        # IMAGE
        # ===========================================================

        if image_url:

            image_path = (
                job_dir /
                "input_image"
            )

            download_file(
                url=image_url,
                destination=image_path,
            )

            markdown, results = process_image(
                image_path
            )

            response = {
                "success": True,
                "type": "image",
                "markdown": markdown,
            }

            if RETURN_JSON:

                response["results"] = results

            return response

        # ===========================================================
        # PDF
        # ===========================================================

        if pdf_url:

            pdf_path = (
                job_dir /
                "input.pdf"
            )

            download_file(
                url=pdf_url,
                destination=pdf_path,
            )

            markdown, results, page_count = process_pdf(
                pdf_path
            )

            response = {
                "success": True,
                "type": "pdf",
                "pages": page_count,
                "markdown": markdown,
            }

            if RETURN_JSON:

                response["results"] = results

            return response

        return {
            "success": False,
            "error": "Unsupported input.",
        }

    except Exception as exc:

        logger.exception(
            "RunPod job %s failed.",
            job_id,
        )

        return {
            "success": False,
            "error": str(exc),
        }

    finally:

        cleanup_job_directory(
            job_dir
        )


# ---------------------------------------------------------------------------
# Start RunPod worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    logger.info(
        "Starting RunPod Serverless worker..."
    )

    logger.info(
        "TEMP_DIR=%s",
        TEMP_DIR,
    )

    logger.info(
        "PADDLEOCR_DEVICE=%s",
        DEVICE,
    )

    runpod.serverless.start(
        {
            "handler": handler,
        }
    )
