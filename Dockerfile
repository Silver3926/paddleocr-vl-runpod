FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOME=/app
ENV PADDLE_PDX_CACHE_HOME=/app/.paddlex
ENV HF_HOME=/app/.huggingface

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    git \
    wget \
    curl \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install \
    --upgrade \
    pip \
    setuptools \
    wheel

# CUDA 11.8 build of PaddlePaddle: runs on hosts with driver >= 450,
# while the cu126 build required driver >= 560 (CUDA 12.6) and got
# rejected by nvidia-container-cli on older hosts:
#   "unsatisfied condition: cuda>=12.6"
RUN python3 -m pip install \
    "paddlepaddle-gpu>=3.2,<3.3" \
    -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

COPY requirements.txt /app/requirements.txt

RUN python3 -m pip install \
    -r /app/requirements.txt

# Bake the PaddleOCR-VL model weights into the image so that workers do not
# download them (multi-GB) on every cold start.
#
# This layer is intentionally placed BEFORE "COPY . /app/" so that code
# changes do not invalidate the large model layer on registry pulls.
#
# NOTE: build runners have no NVIDIA driver, and paddlepaddle-gpu cannot
# even be imported there (libpaddle links against libcuda.so.1). So the
# download runs with the CPU build of PaddlePaddle in a throwaway
# directory that shadows the GPU build via PYTHONPATH. The downloaded
# weights are device-agnostic and are loaded onto the GPU at runtime.
RUN pip install --no-cache-dir --target /opt/bake-deps \
        "paddlepaddle>=3.2,<3.3" \
        "paddleocr[doc-parser]==3.6.0" \
    && PYTHONPATH=/opt/bake-deps \
       python3 -c "from paddleocr import PaddleOCRVL; PaddleOCRVL(pipeline_version='v1.6', device='cpu')" \
    && du -sh /app/.paddlex /app/.huggingface \
    && rm -rf /opt/bake-deps

COPY . /app/

RUN mkdir -p \
    /app/.paddlex \
    /app/.huggingface \
    /app/tmp \
    /tmp/paddleocr

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
