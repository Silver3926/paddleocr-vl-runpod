```python
import os


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def get_bool(
    name: str,
    default: bool,
) -> bool:
    """
    Read a boolean environment variable.
    """

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


def get_int(
    name: str,
    default: int,
) -> int:
    """
    Read an integer environment variable.
    """

    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)

    except ValueError as exc:

        raise ValueError(
            f"Environment variable {name} "
            f"must be an integer."
        ) from exc


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
# Multi-page document restructuring
# ---------------------------------------------------------------------------

MERGE_TABLES = get_bool(
    "PADDLEOCR_MERGE_TABLES",
    True,
)

RELEVEL_TITLES = get_bool(
    "PADDLEOCR_RELEVEL_TITLES",
    True,
)

CONCATENATE_PAGES = get_bool(
    "PADDLEOCR_CONCATENATE_PAGES",
    True,
)


# ---------------------------------------------------------------------------
# PDF processing
# ---------------------------------------------------------------------------

MAX_PDF_PAGES = get_int(
    "MAX_PDF_PAGES",
    500,
)

if MAX_PDF_PAGES <= 0:
    raise ValueError(
        "MAX_PDF_PAGES must be greater than 0."
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

RETURN_JSON = get_bool(
    "RETURN_JSON",
    True,
)


# ---------------------------------------------------------------------------
# Temporary storage
# ---------------------------------------------------------------------------

TEMP_DIR = os.getenv(
    "TEMP_DIR",
    "/tmp/paddleocr",
)


# ---------------------------------------------------------------------------
# Model/cache directories
# ---------------------------------------------------------------------------

HF_HOME = os.getenv(
    "HF_HOME",
    "/app/.huggingface",
)

PADDLE_PDX_CACHE_HOME = os.getenv(
    "PADDLE_PDX_CACHE_HOME",
    "/app/.paddlex",
)


# ---------------------------------------------------------------------------
# Input limits
# ---------------------------------------------------------------------------

MAX_DOWNLOAD_SIZE_MB = get_int(
    "MAX_DOWNLOAD_SIZE_MB",
    500,
)

if MAX_DOWNLOAD_SIZE_MB <= 0:
    raise ValueError(
        "MAX_DOWNLOAD_SIZE_MB must be greater than 0."
    )
```
