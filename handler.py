import json
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
    MAX_OUTPUT_SIZE_MB,
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
        return {
            str(key): make_json_safe(item)
            for key, item in value.items()
        }
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
        markdown = markdown.get("markdown_texts", markdown.get("text", ""))
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


def process_results(results: list[Any]) -> tuple[str, list[Any]]:
    markdown_parts = []
    json_results = []
    for index, result in enumerate(results, start=1):
        markdown = get_result_markdown(result)
        if markdown:
            markdown_parts.append(f"<!-- Result {index} -->\n\n{markdown}")
        if RETURN_JSON:
            json_results.append({"result": get_result_json(result)})
    return "\n\n".join(markdown_parts), json_results


def process_pdf(pdf_path: Path) -> tuple[str, list[Any], int]:
    page_count = validate_input_file(pdf_path, "pdf")
    pages = list(pipeline.predict(input=str(pdf_path)))
    if not pages:
        raise ValueError("PaddleOCR-VL returned no results.")

    processed_results = pages
    if len(pages) > 1:
        try:
            restructured = pipeline.restructure_pages(
                pages,
                merge_tables=MERGE_TABLES,
                relevel_titles=RELEVEL_TITLES,
                concatenate_pages=CONCATENATE_PAGES,
            )
            restructured_results = list(restructured)
            if restructured_results:
                processed_results = restructured_results
        except Exception:
            logger.warning("Multi-page restructuring failed; using page results.")

    markdown, results = process_results(processed_results)
    return markdown, results, page_count


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

    limit = MAX_OUTPUT_SIZE_MB * 1024 * 1024
    if len(payload) > limit:
        raise OutputTooLargeError("OCR response exceeds the configured size limit.")
    return response


def public_error(message: str, code: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": message,
        "error_code": code,
    }


def handler(job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        return public_error("RunPod job must be an object.", "INVALID_JOB")

    job_id = job.get("id", str(uuid.uuid4()))
    job_input = job.get("input", {})
    if not isinstance(job_input, dict):
        return public_error("input must be an object.", "INVALID_INPUT")

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
        else:
            pdf_url = validate_url_input(pdf_url, "pdf_url")
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
            markdown, results, page_count = process_pdf(pdf_path)
            response = {
                "success": True,
                "type": "pdf",
                "pages": page_count,
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
