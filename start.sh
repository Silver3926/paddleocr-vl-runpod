#!/usr/bin/env bash

set -euo pipefail

echo "=========================================="
echo " PaddleOCR-VL 1.6 - RunPod Serverless"
echo "=========================================="

export PADDLEOCR_PIPELINE_VERSION="${PADDLEOCR_PIPELINE_VERSION:-v1.6}"
export PADDLEOCR_DEVICE="${PADDLEOCR_DEVICE:-gpu}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
export RETURN_JSON="${RETURN_JSON:-true}"
export PADDLEOCR_MERGE_TABLES="${PADDLEOCR_MERGE_TABLES:-true}"
export PADDLEOCR_RELEVEL_TITLES="${PADDLEOCR_RELEVEL_TITLES:-true}"
export PADDLEOCR_CONCATENATE_PAGES="${PADDLEOCR_CONCATENATE_PAGES:-true}"
export MAX_PDF_PAGES="${MAX_PDF_PAGES:-500}"
export MAX_DOWNLOAD_SIZE_MB="${MAX_DOWNLOAD_SIZE_MB:-500}"
export TEMP_DIR="${TEMP_DIR:-/tmp/paddleocr}"
export PADDLE_PDX_CACHE_HOME="${PADDLE_PDX_CACHE_HOME:-/app/.paddlex}"
export HF_HOME="${HF_HOME:-/app/.huggingface}"

mkdir -p "${TEMP_DIR}"
mkdir -p "${PADDLE_PDX_CACHE_HOME}"
mkdir -p "${HF_HOME}"

echo ""
echo "Environment:"
echo "PADDLEOCR_PIPELINE_VERSION=${PADDLEOCR_PIPELINE_VERSION}"
echo "PADDLEOCR_DEVICE=${PADDLEOCR_DEVICE}"
echo "PADDLE_PDX_CACHE_HOME=${PADDLE_PDX_CACHE_HOME}"
echo "HF_HOME=${HF_HOME}"
echo "MAX_PDF_PAGES=${MAX_PDF_PAGES}"
echo "MAX_DOWNLOAD_SIZE_MB=${MAX_DOWNLOAD_SIZE_MB}"
echo ""

echo "Python:"
python3 --version
python3 -m pip --version

echo ""
echo "Checking PaddlePaddle..."

python3 - <<'PY'
import paddle

print("PaddlePaddle version:", paddle.__version__)

compiled_with_cuda = paddle.is_compiled_with_cuda()
print("Compiled with CUDA:", compiled_with_cuda)

if not compiled_with_cuda:
    raise RuntimeError(
        "PaddlePaddle is not compiled with CUDA."
    )

device_count = paddle.device.cuda.device_count()
print("CUDA device count:", device_count)
print("Current device:", paddle.device.get_device())

if device_count <= 0:
    raise RuntimeError(
        "No CUDA GPU was detected."
    )
PY

echo ""
echo "Checking NVIDIA GPU..."

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi \
        --query-gpu=name,memory.total,memory.free,driver_version \
        --format=csv,noheader
else
    echo "nvidia-smi is not available."
fi

echo ""
echo "Checking PaddleOCR..."

python3 - <<'PY'
import paddleocr

print(
    "PaddleOCR version:",
    getattr(
        paddleocr,
        "__version__",
        "unknown",
    ),
)

from paddleocr import PaddleOCRVL

print(
    "PaddleOCRVL import: OK"
)
PY

echo ""
echo "Starting RunPod Serverless worker..."
echo ""

exec python3 -u /app/handler.py
