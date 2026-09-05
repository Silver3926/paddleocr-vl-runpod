import os


def get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


# ---------------------------------------------------------------------------
# PaddleOCR-VL
# ---------------------------------------------------------------------------

PIPELINE_VERSION = os.getenv(
    "PADDLEOCR_PIPELINE_VERSION",
    "v1.6",
)

DEVICE = os.getenv(
    "PADDLEOCR_DEVICE",
    "gpu",
)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
)


# ---------------------------------------------------------------------------
# Input / output
# ---------------------------------------------------------------------------

MAX_PDF_PAGES = int(
    os.getenv(
        "MAX_PDF_PAGES",
        "0",
    )
)

OUTPUT_FORMAT = os.getenv(
    "OUTPUT_FORMAT",
    "markdown",
)

RETURN_JSON = get_bool(
    "RETURN_JSON",
    True,
)


# ---------------------------------------------------------------------------
# Temporary files
# ---------------------------------------------------------------------------

TEMP_DIR = os.getenv(
    "TEMP_DIR",
    "/tmp/paddleocr",
)


# ---------------------------------------------------------------------------
# Model/cache
# ---------------------------------------------------------------------------

HF_HOME = os.getenv(
    "HF_HOME",
    "/tmp/huggingface",
)

PADDLE_HOME = os.getenv(
    "PADDLE_HOME",
    "/tmp/paddle",
)