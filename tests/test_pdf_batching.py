import fitz
import pytest

from pdf_batching import (
    PdfBatch,
    build_pdf_batches,
    parse_pdf_batch_options,
    resolve_page_range,
)
from pdf_processor import split_pdf_batch


def create_test_pdf(path, page_count):
    document = fitz.open()
    for index in range(page_count):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    document.save(path)
    document.close()


def test_parse_defaults():
    options = parse_pdf_batch_options({})

    assert options.page_start is None
    assert options.page_end is None
    assert options.batch_size == 5


def test_parse_page_range_and_batch_size():
    options = parse_pdf_batch_options({
        "page_start": 11,
        "page_end": 20,
        "batch_size": 3,
    })

    assert options.page_start == 11
    assert options.page_end == 20
    assert options.batch_size == 3


def test_resolve_page_range_defaults_to_document():
    assert resolve_page_range(12) == (1, 12)


def test_resolve_page_range_rejects_out_of_bounds():
    with pytest.raises(ValueError, match="page count"):
        resolve_page_range(12, page_start=1, page_end=13)


def test_resolve_page_range_rejects_reversed_range():
    with pytest.raises(ValueError, match="page_start"):
        resolve_page_range(12, page_start=8, page_end=4)


def test_build_batches_exact_multiple():
    batches = build_pdf_batches(1, 10, batch_size=5)

    assert [
        (batch.batch_id, batch.page_start, batch.page_end)
        for batch in batches
    ] == [
        ("batch-0001", 1, 5),
        ("batch-0002", 6, 10),
    ]


def test_build_batches_with_remainder():
    batches = build_pdf_batches(1, 12, batch_size=5)

    assert [
        (batch.page_start, batch.page_end, batch.page_count)
        for batch in batches
    ] == [
        (1, 5, 5),
        (6, 10, 5),
        (11, 12, 2),
    ]


def test_build_batches_non_one_start():
    batches = build_pdf_batches(11, 20, batch_size=3)

    assert [
        (batch.page_start, batch.page_end)
        for batch in batches
    ] == [
        (11, 13),
        (14, 16),
        (17, 19),
        (20, 20),
    ]


def test_split_pdf_batch_uses_one_based_inclusive_range(tmp_path):
    source = tmp_path / "source.pdf"
    destination = tmp_path / "batch.pdf"
    create_test_pdf(source, page_count=5)

    split_pdf_batch(
        source_pdf=source,
        destination_pdf=destination,
        batch=PdfBatch("batch-0001", 2, 4),
    )

    result = fitz.open(destination)
    try:
        assert len(result) == 3
        assert "Page 2" in result[0].get_text()
        assert "Page 4" in result[2].get_text()
    finally:
        result.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"page_start": 0},
        {"page_end": 0},
        {"batch_size": 0},
        {"page_start": True},
        {"batch_size": "5"},
        {"page_start": 8, "page_end": 4},
    ],
)
def test_invalid_batch_options(payload):
    with pytest.raises(ValueError):
        parse_pdf_batch_options(payload)
