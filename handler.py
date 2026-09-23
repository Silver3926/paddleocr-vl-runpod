import json
import logging
import uuid
from pathlib import Path
from typing import Any

import fitz
import runpod
from paddleocr import PaddleOCRVL

from batch_execution import (
    ProgressCallback,
    execute_batch_with_retry,
)
from batch_retry import BatchStatus
from config import (
    CONCATENATE_PAGES,
    DEVICE,
    LOG_LEVEL,
    MAX_OUTPUT_SIZE_MB,
    MERGE_TABLES,
    PIPELINE_VERSION,
    RELEVEL_TITLES,
    RETURN_JSON,
    TEMP_DIR,
)
from pdf_batching import (
    PdfBatchOptions,
    build_pdf_batches,
    parse_pdf_batch_options,
    resolve_page_range,
)
from pdf_processor import (
    cleanup_job_directory,
    create_job_directory,
    download_file,
    validate_input_file,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

logger.info("Initializing PaddleOCR-VL version %s on %s", PIPELINE_VERSION, DEVICE)
try:
    pipeline = PaddleOCRVL(
        pipeline_version=PIPELINE_VERSION,
        device=DEVICE,
    )
except Exception as exc:
    logger.exception("Failed to initialize PaddleOCR-VL.")
    raise RuntimeError("PaddleOCR-VL initialization failed.") from exc


class OutputTooLargeError(ValueError):
    """Raised when the inline RunPod response exceeds the configured limit."""


def make_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return make_json_safe(value.tolist())
    return str(value)


def get_result_markdown(result: Any) -> str:
    markdown = getattr(result, "markdown", None)
    if markdown is None and isinstance(result, dict):
        markdown = result.get("markdown")
    if isinstance(markdown, dict):
        markdown = markdown.get(
            "markdown_texts",
            markdown.get("text", ""),
        )
    if isinstance(markdown, list):
        return "\n\n".join(str(item) for item in markdown if item)
    return markdown if isinstance(markdown, str) else ""


def get_result_json(result: Any) -> Any:
    value = getattr(result, "json", None)
    if callable(value):
        try:
            value = value()
        except Exception:
            logger.warning("Unable to extract structured OCR result.")
            value = None
    if value is None and isinstance(result, dict):
        value = result
    if value is None:
        value = str(result)
    return make_json_safe(value)


def process_results(
    results: list[Any],
    page_numbers: list[int | list[int]] | None = None,
) -> tuple[str, list[Any]]:
    """Serialize results while retaining original PDF page numbers."""

    if page_numbers is not None and len(page_numbers) != len(results):
        raise ValueError("Page number metadata does not match result count.")

    markdown_parts = []
    json_results = []
    for index, result in enumerate(results, start=1):
        markdown = get_result_markdown(result)
        page_number = None if page_numbers is None else page_numbers[index - 1]

        if markdown:
            if page_number is None:
                marker = f"<!-- Result {index} -->"
            elif isinstance(page_number, list):
                marker = f"<!-- Pages {page_number[0]}-{page_number[-1]} -->"
            else:
                marker = f"<!-- Page {page_number} -->"
            markdown_parts.append(f"{marker}\n\n{markdown}")

        if RETURN_JSON:
            item = {"result": get_result_json(result)}
            if page_number is not None:
                item["page_numbers"] = (
                    page_number
                    if isinstance(page_number, list)
                    else [page_number]
                )
            json_results.append(item)

    return "\n\n".join(markdown_parts), json_results


def process_pdf(
    pdf_path: Path,
    pipeline_instance: Any,
    batch_options: PdfBatchOptions,
    progress: ProgressCallback | None = None,
) -> tuple[str, list[Any], int, int, int, int]:
    """Process selected PDF pages sequentially with retry and progress logs."""

    total_pages = validate_input_file(pdf_path, "pdf")
    page_start, page_end = resolve_page_range(
        total_pages=total_pages,
        page_start=batch_options.page_start,
        page_end=batch_options.page_end,
    )
    batches = build_pdf_batches(
        page_start=page_start,
        page_end=page_end,
        batch_size=batch_options.batch_size,
    )

    pages = []
    page_numbers: list[int] = []
    completed_batches = 0
    batch_statuses = []

    def report_progress(status) -> None:
        nonlocal completed_batches
        batch_statuses.append(status)
        if progress is not None:
            progress(status)
        if status.status is not BatchStatus.COMPLETED:
            return
        completed_batches += 1
        progress_percent = int(completed_batches / len(batches) * 100)
        logger.info(
            "batch_progress completed_batches=%s total_batches=%s "
            "progress_percent=%s last_batch_id=%s",
            completed_batches,
            len(batches),
            progress_percent,
            status.batch_id,
        )

    source_document = fitz.open(str(pdf_path))
    try:
        for batch in batches:
            batch_path = pdf_path.parent / f"{batch.batch_id}.pdf"
            batch_pages, status = execute_batch_with_retry(
                pipeline_instance=pipeline_instance,
                source_document=source_document,
                batch=batch,
                batch_path=batch_path,
                progress=report_progress,
            )
            pages.extend(batch_pages)
            page_numbers.extend(range(batch.page_start, batch.page_end + 1))
            logger.debug(
                "batch_result batch_id=%s status=%s attempts=%s",
                status.batch_id,
                status.status,
                status.attempts,
            )
    finally:
        source_document.close()

    processed_results = pages
    processed_page_numbers: list[int | list[int]] = list(page_numbers)
    if len(pages) > 1:
        try:
            restructured_results = list(
                pipeline_instance.restructure_pages(
                    pages,
                    merge_tables=MERGE_TABLES,
                    relevel_titles=RELEVEL_TITLES,
                    concatenate_pages=CONCATENATE_PAGES,
                )
            )
            if len(restructured_results) == len(page_numbers):
                processed_results = restructured_results
            elif len(restructured_results) == 1:
                processed_results = restructured_results
                processed_page_numbers = [list(page_numbers)]
            else:
                logger.warning(
                    "Multi-page restructuring returned %s results for %s "
                    "pages; using page-level results to preserve page numbers.",
                    len(restructured_results),
                    len(page_numbers),
                )
        except Exception:
            logger.warning(
                "Multi-page restructuring failed; using page results."
            )

    markdown, results = process_results(
        processed_results,
        page_numbers=processed_page_numbers,
    )
    return (
        markdown,
        results,
        total_pages,
        page_start,
        page_end,
        len(batches),
    )


def process_image(image_path: Path) -> tuple[str, list[Any]]:
    validate_input_file(image_path, "image")
    results = list(pipeline.predict(input=str(image_path)))
    if not results:
        raise ValueError("PaddleOCR-VL returned no results.")
    return process_results(results)


def validate_url_input(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' must be a non-empty string.")
    if not value.strip().lower().startswith("https://"):
        raise ValueError(f"'{field_name}' must use HTTPS.")
    return value.strip()


def response_with_size_limit(response: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.dumps(
            response,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("OCR response could not be serialized as JSON.") from exc

    if len(payload) > MAX_OUTPUT_SIZE_MB * 1024 * 1024:
        raise OutputTooLargeError(
            "OCR response exceeds the configured size limit."
        )
    return response


def public_error(message: str, code: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": message,
        "error_code": code,
    }


def handler(job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        return public_error(
            "RunPod job must be an object.",
            "INVALID_JOB",
        )

    job_id = job.get("id", str(uuid.uuid4()))
    job_input = job.get("input", {})
    if not isinstance(job_input, dict):
        return public_error(
            "input must be an object.",
            "INVALID_INPUT",
        )

    image_url = job_input.get("image_url")
    pdf_url = job_input.get("pdf_url")
    if bool(image_url) == bool(pdf_url):
        return public_error(
            "Provide exactly one of 'image_url' or 'pdf_url'.",
            "INVALID_INPUT",
        )

    try:
        if image_url:
            image_url = validate_url_input(image_url, "image_url")
            batch_options = None
        else:
            pdf_url = validate_url_input(pdf_url, "pdf_url")
            batch_options = parse_pdf_batch_options(job_input)
    except ValueError as exc:
        return public_error(str(exc), "INVALID_INPUT")

    job_dir = create_job_directory(job_id)
    try:
        if image_url:
            image_path = job_dir / "input_image"
            download_file(image_url, image_path)
            markdown, results = process_image(image_path)
            response = {
                "success": True,
                "type": "image",
                "markdown": markdown,
            }
        else:
            pdf_path = job_dir / "input.pdf"
            download_file(pdf_url, pdf_path)
            (
                markdown,
                results,
                total_pages,
                page_start,
                page_end,
                batch_count,
            ) = process_pdf(pdf_path, pipeline, batch_options)
            response = {
                "success": True,
                "type": "pdf",
                "pages": page_end - page_start + 1,
                "document_pages": total_pages,
                "batches": batch_count,
                "page_start": page_start,
                "page_end": page_end,
                "markdown": markdown,
            }

        if RETURN_JSON:
            response["results"] = results
        return response_with_size_limit(response)

    except OutputTooLargeError:
        logger.exception("Job output exceeded MAX_OUTPUT_SIZE_MB.")
        return public_error(
            "OCR output is too large for an inline response.",
            "OUTPUT_TOO_LARGE",
        )
    except Exception:
        logger.exception("RunPod job failed: %s", job_id)
        return public_error(
            "Document processing failed.",
            "PROCESSING_ERROR",
        )
    finally:
        cleanup_job_directory(job_dir)


if __name__ == "__main__":
    logger.info("Starting RunPod worker; TEMP_DIR=%s", TEMP_DIR)
    runpod.serverless.start({"handler": handler})
