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

RUN python3 -m pip install \
    https://paddle-whl.bj.bcebos.com/nightly/cu126/safetensors/safetensors-0.6.2.dev0-cp38-abi3-linux_x86_64.whl

COPY requirements.txt /app/requirements.txt

RUN python3 -m pip install \
    -r /app/requirements.txt

COPY . /app/

RUN mkdir -p \
    /app/.paddlex \
    /app/.huggingface \
    /app/tmp \
    /tmp/paddleocr

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]

