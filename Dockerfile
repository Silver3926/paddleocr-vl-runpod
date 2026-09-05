FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

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

RUN python3 -m pip install \
    paddlepaddle-gpu==3.2.1 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

COPY requirements.txt /app/requirements.txt

RUN python3 -m pip install \
    -r /app/requirements.txt

# Bake the PaddleOCR-VL model weights into the image so that workers do not
# download them (multi-GB) on every cold start.
#
# This layer is intentionally placed BEFORE "COPY . /app/" so that code
# changes do not invalidate the large model layer on registry pulls.
#
# The build runner has no GPU, so the download runs on CPU; the weights
# are device-agnostic and are loaded onto the GPU at runtime.
RUN python3 -c "from paddleocr import PaddleOCRVL; PaddleOCRVL(pipeline_version='v1.6', device='cpu')" \
    && du -sh /app/.paddlex /app/.huggingface

COPY . /app/

RUN mkdir -p \
    /app/.paddlex \
    /app/.huggingface \
    /app/tmp \
    /tmp/paddleocr

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
