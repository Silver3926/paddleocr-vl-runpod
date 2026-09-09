import importlib
import sys
import types

import pytest


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
