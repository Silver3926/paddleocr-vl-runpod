import fitz
import importlib
import sys
import types
from pathlib import Path

import pytest

from pdf_batching import PdfBatchOptions


@pytest.fixture
def handler_module(monkeypatch):
    fake_runpod = types.ModuleType("runpod")
    fake_runpod.serverless = types.SimpleNamespace(start=lambda config: None)

    fake_paddleocr = types.ModuleType("paddleocr")

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_paddleocr.PaddleOCRVL = FakePipeline
    monkeypatch.setitem(sys.modules, "runpod", fake_runpod)
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)
    sys.modules.pop("handler", None)
    module = importlib.import_module("handler")
    return module


def test_handler_rejects_non_object(handler_module):
    result = handler_module.handler(None)
    assert result == {
        "success": False,
        "error": "RunPod job must be an object.",
        "error_code": "INVALID_JOB",
    }


def test_handler_requires_exactly_one_input(handler_module):
    result = handler_module.handler({"input": {}})
    assert result["success"] is False
    assert result["error_code"] == "INVALID_INPUT"


def test_handler_rejects_http(handler_module):
    result = handler_module.handler({
        "input": {"pdf_url": "http://example.com/file.pdf"}
    })
    assert result["success"] is False
    assert result["error_code"] == "INVALID_INPUT"


def test_handler_rejects_two_inputs(handler_module):
    result = handler_module.handler({
        "input": {
            "image_url": "https://example.com/image.png",
            "pdf_url": "https://example.com/file.pdf",
        }
    })
    assert result["success"] is False
    assert result["error_code"] == "INVALID_INPUT"


def test_json_safe_converts_numpy_like_values(handler_module):
    class ArrayLike:
        def tolist(self):
            return [1, 2, {"x": 3}]

    assert handler_module.make_json_safe(ArrayLike()) == [1, 2, {"x": 3}]


def test_response_size_limit(handler_module, monkeypatch):
    monkeypatch.setattr(handler_module, "MAX_OUTPUT_SIZE_MB", 1)
    response = handler_module.response_with_size_limit({
        "success": True,
        "markdown": "ok",
    })
    assert response["success"] is True

    monkeypatch.setattr(handler_module, "MAX_OUTPUT_SIZE_MB", 0.000001)
    with pytest.raises(handler_module.OutputTooLargeError):
        handler_module.response_with_size_limit({
            "success": True,
            "markdown": "x" * 100,
        })


def test_process_pdf_runs_batches_sequentially_and_preserves_pages(
    handler_module,
    tmp_path,
):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    for index in range(6):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    document.save(source)
    document.close()

    class BatchPipeline:
        def __init__(self):
            self.inputs = []

        def predict(self, input):
            self.inputs.append(input)
            batch_document = fitz.open(input)
            try:
                return [
                    {"markdown": f"page {index + 1}"}
                    for index in range(batch_document.page_count)
                ]
            finally:
                batch_document.close()

        def restructure_pages(self, pages, **kwargs):
            return pages

    fake_pipeline = BatchPipeline()
    result = handler_module.process_pdf(
        source,
        fake_pipeline,
        PdfBatchOptions(page_start=2, page_end=6, batch_size=2),
    )

    assert len(fake_pipeline.inputs) == 3
    assert [Path(path).name for path in fake_pipeline.inputs] == [
        "batch-0001.pdf",
        "batch-0002.pdf",
        "batch-0003.pdf",
    ]
    assert result[2:] == (6, 2, 6, 3)
    assert "<!-- Page 2 -->" in result[0]
    assert "<!-- Page 6 -->" in result[0]
    assert [item["page_numbers"] for item in result[1]] == [
        [2],
        [3],
        [4],
        [5],
        [6],
    ]
    assert list(tmp_path.glob("batch-*.pdf")) == []


def test_process_results_preserves_all_pages_for_single_restructured_result(
    handler_module,
):
    markdown, results = handler_module.process_results(
        [{"markdown": "combined"}],
        page_numbers=[[4, 5, 6]],
    )

    assert "<!-- Pages 4-6 -->" in markdown
    assert results[0]["page_numbers"] == [4, 5, 6]
