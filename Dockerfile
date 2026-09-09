FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app \
    PADDLE_PDX_CACHE_HOME=/app/.paddlex \
    HF_HOME=/app/.huggingface

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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

RUN python3 -m pip install --upgrade \
    pip \
    setuptools \
    wheel

RUN python3 -m pip install \
    paddlepaddle-gpu==3.2.1 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --requirement /app/requirements.txt

# Download model weights during the build using the CPU PaddlePaddle package.
# The weights are device-independent; the runtime uses the GPU package above.
RUN python3 -m pip install --no-cache-dir --target /opt/bake-deps \
        paddlepaddle==3.2.1 \
        paddleocr[doc-parser]==3.6.0 \
    && PYTHONPATH=/opt/bake-deps \
       python3 -c "from paddleocr import PaddleOCRVL; PaddleOCRVL(pipeline_version='v1.6', device='cpu')" \
    && rm -rf /opt/bake-deps

COPY . /app/

RUN mkdir -p \
        /app/.paddlex \
        /app/.huggingface \
        /app/tmp \
        /tmp/paddleocr \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /tmp/paddleocr \
    && chmod +x /app/start.sh

USER appuser

CMD ["/app/start.sh"]
