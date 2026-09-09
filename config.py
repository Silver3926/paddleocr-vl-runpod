import os


def get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"Environment variable {name} must be boolean.")


def get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be an integer."
        ) from exc


PIPELINE_VERSION = os.getenv("PADDLEOCR_PIPELINE_VERSION", "v1.6")
DEVICE = os.getenv("PADDLEOCR_DEVICE", "gpu").strip().lower()
if DEVICE not in {"gpu", "cpu"}:
    raise ValueError("PADDLEOCR_DEVICE must be either 'gpu' or 'cpu'.")

MERGE_TABLES = get_bool("PADDLEOCR_MERGE_TABLES", True)
RELEVEL_TITLES = get_bool("PADDLEOCR_RELEVEL_TITLES", True)
CONCATENATE_PAGES = get_bool("PADDLEOCR_CONCATENATE_PAGES", True)

MAX_PDF_PAGES = get_int("MAX_PDF_PAGES", 500)
MAX_DOWNLOAD_SIZE_MB = get_int("MAX_DOWNLOAD_SIZE_MB", 500)
MAX_OUTPUT_SIZE_MB = get_int("MAX_OUTPUT_SIZE_MB", 25)
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = get_int(
    "DOWNLOAD_CONNECT_TIMEOUT_SECONDS", 10
)
DOWNLOAD_READ_TIMEOUT_SECONDS = get_int(
    "DOWNLOAD_READ_TIMEOUT_SECONDS", 120
)

for name, value in {
    "MAX_PDF_PAGES": MAX_PDF_PAGES,
    "MAX_DOWNLOAD_SIZE_MB": MAX_DOWNLOAD_SIZE_MB,
    "MAX_OUTPUT_SIZE_MB": MAX_OUTPUT_SIZE_MB,
    "DOWNLOAD_CONNECT_TIMEOUT_SECONDS": DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
    "DOWNLOAD_READ_TIMEOUT_SECONDS": DOWNLOAD_READ_TIMEOUT_SECONDS,
}.items():
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
RETURN_JSON = get_bool("RETURN_JSON", True)
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp/paddleocr")
HF_HOME = os.getenv("HF_HOME", "/app/.huggingface")
PADDLE_PDX_CACHE_HOME = os.getenv("PADDLE_PDX_CACHE_HOME", "/app/.paddlex")
