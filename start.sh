#!/usr/bin/env bash

set -e

echo "=========================================="
echo " PaddleOCR-VL 1.6 - RunPod Serverless"
echo "=========================================="

echo "Python version:"
python3 --version

echo ""
echo "Checking PaddlePaddle..."

python3 - <<'PY'
import paddle

print("PaddlePaddle version:", paddle.__version__)
print("Compiled with CUDA:", paddle.is_compiled_with_cuda())

if paddle.is_compiled_with_cuda():
    print("CUDA device count:", paddle.device.cuda.device_count())
    print("Current device:", paddle.device.get_device())
else:
    print("WARNING: PaddlePaddle was not compiled with CUDA.")
PY

echo ""
echo "Creating directories..."

mkdir -p "${TEMP_DIR:-/tmp/paddleocr}"
mkdir -p "${HF_HOME:-/tmp/huggingface}"
mkdir -p "${PADDLE_HOME:-/tmp/paddle}"

echo ""
echo "Environment:"
echo "PADDLEOCR_PIPELINE_VERSION=${PADDLEOCR_PIPELINE_VERSION:-v1.6}"
echo "PADDLEOCR_DEVICE=${PADDLEOCR_DEVICE:-gpu}"
echo "MAX_PDF_PAGES=${MAX_PDF_PAGES:-0}"
echo "OUTPUT_FORMAT=${OUTPUT_FORMAT:-markdown}"
echo "RETURN_JSON=${RETURN_JSON:-true}"
echo "HF_HOME=${HF_HOME:-/tmp/huggingface}"
echo "PADDLE_HOME=${PADDLE_HOME:-/tmp/paddle}"

echo ""
echo "Starting RunPod worker..."
echo ""

exec python3 /app/handler.py