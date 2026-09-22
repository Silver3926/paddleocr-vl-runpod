from dataclasses import dataclass
from typing import Any, Mapping

from config import MAX_PDF_BATCH_SIZE, PDF_BATCH_SIZE


@dataclass(frozen=True)
class PdfBatchOptions:
    """Validated PDF processing options using one-based inclusive page numbers."""

    page_start: int | None = None
    page_end: int | None = None
    batch_size: int = PDF_BATCH_SIZE


@dataclass(frozen=True)
class PdfBatch:
    """A one-based, inclusive range of pages assigned to one batch."""

    batch_id: str
    page_start: int
    page_end: int

    @property
    def page_count(self) -> int:
        return self.page_end - self.page_start + 1


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{field_name}' must be an integer.")
    if value < 1:
        raise ValueError(f"'{field_name}' must be greater than zero.")
    return value


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"'{field_name}' must be an integer.")
    if value < 1:
        raise ValueError(f"'{field_name}' must be greater than zero.")
    return value


def parse_pdf_batch_options(
    input_data: Mapping[str, Any],
) -> PdfBatchOptions:
    """Parse the public PDF batching contract without touching the PDF yet."""

    page_start = _optional_positive_int(
        input_data.get("page_start"),
        "page_start",
    )
    page_end = _optional_positive_int(
        input_data.get("page_end"),
        "page_end",
    )
    batch_size = input_data.get("batch_size", PDF_BATCH_SIZE)
    batch_size = _positive_int(batch_size, "batch_size")

    if batch_size > MAX_PDF_BATCH_SIZE:
        raise ValueError(
            f"'batch_size' cannot exceed {MAX_PDF_BATCH_SIZE}."
        )

    if (
        page_start is not None
        and page_end is not None
        and page_start > page_end
    ):
        raise ValueError("'page_start' cannot be greater than 'page_end'.")

    return PdfBatchOptions(
        page_start=page_start,
        page_end=page_end,
        batch_size=batch_size,
    )


def resolve_page_range(
    total_pages: int,
    page_start: int | None = None,
    page_end: int | None = None,
) -> tuple[int, int]:
    """Validate and resolve a one-based inclusive range against a PDF."""

    if isinstance(total_pages, bool) or not isinstance(total_pages, int):
        raise ValueError("total_pages must be an integer.")
    if total_pages < 1:
        raise ValueError("PDF must contain at least one page.")

    resolved_start = page_start if page_start is not None else 1
    resolved_end = page_end if page_end is not None else total_pages

    _positive_int(resolved_start, "page_start")
    _positive_int(resolved_end, "page_end")

    if resolved_start > resolved_end:
        raise ValueError("'page_start' cannot be greater than 'page_end'.")
    if resolved_end > total_pages:
        raise ValueError(
            f"'page_end' cannot exceed the PDF page count ({total_pages})."
        )

    return resolved_start, resolved_end


def build_pdf_batches(
    page_start: int,
    page_end: int,
    batch_size: int = PDF_BATCH_SIZE,
) -> list[PdfBatch]:
    """Build ordered batches from a one-based inclusive page range."""

    resolved_start, resolved_end = resolve_page_range(
        total_pages=page_end,
        page_start=page_start,
        page_end=page_end,
    )
    batch_size = _positive_int(batch_size, "batch_size")
    if batch_size > MAX_PDF_BATCH_SIZE:
        raise ValueError(
            f"'batch_size' cannot exceed {MAX_PDF_BATCH_SIZE}."
        )

    batches = []
    current_page = resolved_start
    batch_number = 1
    while current_page <= resolved_end:
        current_end = min(current_page + batch_size - 1, resolved_end)
        batches.append(
            PdfBatch(
                batch_id=f"batch-{batch_number:04d}",
                page_start=current_page,
                page_end=current_end,
            )
        )
        current_page = current_end + 1
        batch_number += 1

    return batches
