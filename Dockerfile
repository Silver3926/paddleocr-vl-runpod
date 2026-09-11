FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

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

RUN echo '=== DIAGNOSTIC: after bootstrap tooling ===' \
    && python3 -m pip show pip setuptools wheel || true \
    && find /usr/local/lib/python3.10/dist-packages \
        \( -iname 'msgpack*dist-info' -o -iname 'setuptools*dist-info' \) \
        -print || true

RUN python3 -m pip install \
    paddlepaddle-gpu==3.2.1 \
    -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

RUN echo '=== DIAGNOSTIC: after paddlepaddle-gpu installation ===' \
    && python3 -m pip show paddlepaddle-gpu msgpack setuptools || true \
    && python3 -m pip check || true \
    && find /usr/local/lib/python3.10/dist-packages \
        \( -iname 'msgpack*dist-info' -o -iname 'setuptools*dist-info' \) \
        -print || true

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --requirement /app/requirements.txt

RUN echo '=== DIAGNOSTIC: after requirements.txt installation ===' \
    && python3 -m pip show msgpack protobuf setuptools requests Pillow PyMuPDF || true \
    && python3 -m pip check || true \
    && find /usr/local/lib/python3.10/dist-packages \
        \( -iname 'msgpack*dist-info' -o -iname 'setuptools*dist-info' \) \
        -print || true

# Download device-independent model weights with the CPU PaddlePaddle build.
RUN python3 -m pip install --no-cache-dir --target /opt/bake-deps \
        paddlepaddle==3.2.1 \
        paddleocr[doc-parser]==3.6.0

RUN echo '=== DIAGNOSTIC: packages in /opt/bake-deps ===' \
    && PYTHONPATH=/opt/bake-deps python3 - <<'PY'
import importlib.metadata as metadata
import sys

print("Python executable:", sys.executable)
for name in ("paddlepaddle", "paddleocr", "paddlex", "msgpack", "protobuf", "setuptools"):
    try:
        dist = metadata.distribution(name)
        print(f"{name}: {dist.version} @ {dist.locate_file('')}")
    except metadata.PackageNotFoundError:
        print(f"{name}: NOT INSTALLED")
PY

RUN PYTHONPATH=/opt/bake-deps \
       python3 -c "from paddleocr import PaddleOCRVL; PaddleOCRVL(pipeline_version='v1.6', device='cpu')" \
    && rm -rf /opt/bake-deps

RUN echo '=== DIAGNOSTIC: final runtime environment ===' \
    && python3 -m pip show msgpack protobuf setuptools requests Pillow PyMuPDF || true \
    && python3 -m pip check || true \
    && find /usr/local/lib/python3.10/dist-packages \
        \( -iname 'msgpack*dist-info' -o -iname 'setuptools*dist-info' \) \
        -print || true

COPY . /app/

RUN mkdir -p \
        /app/.paddlex \
        /app/.huggingface \
        /app/.cache \
        /app/.config \
        /app/tmp \
        /tmp/paddleocr \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /tmp/paddleocr \
    && chmod +x /app/start.sh

RUN echo '=== DIAGNOSTIC: final filesystem metadata ===' \
    && find /usr/local/lib/python3.10/dist-packages \
        \( -iname 'msgpack*dist-info' -o -iname 'setuptools*dist-info' \) \
        -print || true \
    && stat -c '%U:%G %A %n' /app /app/.paddlex /app/.huggingface /tmp/paddleocr

USER appuser

CMD ["/app/start.sh"]
