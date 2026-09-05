# PaddleOCR-VL 1.6 — RunPod Serverless Worker

RunPod Serverless worker untuk menjalankan **PaddleOCR-VL 1.6** pada GPU.

Worker menerima:

- URL PDF
- URL image

dan mengembalikan:

- Markdown
- Structured JSON
- jumlah halaman untuk PDF

Target utama project ini adalah OCR dan document parsing untuk dokumen hasil scan yang kemudian dapat digunakan oleh sistem RAG seperti Open Notebook.


## Features

- PaddleOCR-VL 1.6
- PaddlePaddle GPU
- CUDA 12.6
- RunPod Serverless
- PDF processing
- Image processing
- Markdown output
- Structured JSON output
- Multi-page document restructuring
- Table merging
- Title re-leveling
- Page concatenation
- Download size protection
- PDF page limit
- Per-job temporary directory
- GPU validation at startup
- Docker
- GitHub Actions
- GitHub Container Registry (GHCR)


# Architecture

```text
                  ┌─────────────────────┐
                  │      Client         │
                  │                     │
                  │  PDF URL / Image URL│
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ RunPod Serverless   │
                  │                     │
                  │  PaddleOCR-VL 1.6   │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │      Download       │
                  │                     │
                  │  PDF / Image        │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │       Validate      │
                  │                     │
                  │  size / format /    │
                  │  page count         │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │    PaddleOCR-VL     │
                  │                     │
                  │ document parsing    │
                  │ OCR / layout / etc. │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │   Multi-page        │
                  │   restructuring     │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │       Output        │
                  │                     │
                  │ Markdown + JSON     │
                  └─────────────────────┘
Project structure
paddleocr-vl-runpod/
│
├── Dockerfile
├── .dockerignore
├── requirements.txt
├── config.py
├── pdf_processor.py
├── handler.py
├── start.sh
├── README.md
│
└── .github/
    └── workflows/
        └── docker.yml
File responsibilities
Dockerfile

Builds the GPU container.

Main components:

CUDA 12.6
PaddlePaddle GPU 3.2.1
PaddleOCR
RunPod
Python dependencies

The PaddleOCR-VL model itself is downloaded during worker initialization rather than being baked into the Docker image.

requirements.txt

Contains Python dependencies that are installed through pip.

The PaddlePaddle GPU package is installed separately because it uses the official PaddlePaddle CUDA package repository.

config.py

Centralizes configuration.

Configuration is controlled through environment variables.

It contains:

PaddleOCR pipeline version
device
restructuring settings
PDF page limit
download size limit
logging
output settings
cache directories
pdf_processor.py

Handles input files.

Responsibilities:

download URL
download size limit
URL validation
temporary storage
PDF validation
image validation
PDF page count
maximum PDF page limit
cleanup
handler.py

Main RunPod Serverless worker.

Responsibilities:

initialize PaddleOCR-VL
receive RunPod jobs
process images
process PDFs
restructure multi-page documents
produce Markdown
produce JSON
return the RunPod response
start.sh

Container entrypoint.

Responsibilities:

set environment defaults
create cache directories
verify Python
verify PaddlePaddle
verify CUDA
verify GPU
display GPU information
start the RunPod worker
.github/workflows/docker.yml

GitHub Actions workflow.

Every push to main:

GitHub
   ↓
GitHub Actions
   ↓
Docker build
   ↓
GHCR

The image is published to:

ghcr.io/<github-user>/<repository>
Requirements
Hardware

Recommended:

NVIDIA GPU
CUDA-compatible environment

For large scanned documents, more VRAM is preferable.

Software

Development:

Git
Docker
NVIDIA Container Toolkit
Python is optional because the application runs inside Docker

Deployment:

RunPod account
RunPod Serverless endpoint
PaddleOCR-VL

This project uses:

PaddleOCR-VL 1.6

Pipeline:

from paddleocr import PaddleOCRVL

pipeline = PaddleOCRVL(
    pipeline_version="v1.6",
)

PaddleOCR-VL supports document images and PDF input.

For PDFs, PaddleOCR-VL processes the document page by page and can subsequently restructure the page results into a multi-page document.

Configuration

All runtime configuration is controlled through environment variables.

PaddleOCR
PADDLEOCR_PIPELINE_VERSION=v1.6

PADDLEOCR_DEVICE=gpu

Default:

PADDLEOCR_PIPELINE_VERSION=v1.6
PADDLEOCR_DEVICE=gpu
Multi-page restructuring
PADDLEOCR_MERGE_TABLES=true

PADDLEOCR_RELEVEL_TITLES=true

PADDLEOCR_CONCATENATE_PAGES=true

Defaults:

PADDLEOCR_MERGE_TABLES=true
PADDLEOCR_RELEVEL_TITLES=true
PADDLEOCR_CONCATENATE_PAGES=true

These settings are passed to:

pipeline.restructure_pages(
    pages,
    merge_tables=True,
    relevel_titles=True,
    concatenate_pages=True,
)
PDF limit
MAX_PDF_PAGES=500

Default:

500

A PDF exceeding this limit is rejected before OCR processing begins.

Download limit
MAX_DOWNLOAD_SIZE_MB=500

Default:

500 MB

The limit is enforced during streaming download.

Output
RETURN_JSON=true

Set:

RETURN_JSON=false

if only Markdown output is required.

Logging
LOG_LEVEL=INFO

Possible examples:

DEBUG
INFO
WARNING
ERROR
Cache

PaddleX cache:

PADDLE_PDX_CACHE_HOME=/app/.paddlex

Hugging Face cache:

HF_HOME=/app/.huggingface
RunPod input

The worker supports two input types.

Only one should be supplied per job.

Image

Request:

{
  "input": {
    "image_url": "https://example.com/document.png"
  }
}
PDF

Request:

{
  "input": {
    "pdf_url": "https://example.com/document.pdf"
  }
}
Example PDF response
{
  "success": true,
  "type": "pdf",
  "pages": 10,
  "markdown": "<!-- Result 1 -->..."
}

When:

RETURN_JSON=true

the response also contains:

{
  "results": [
    {
      "result": {}
    }
  ]
}
Example image response
{
  "success": true,
  "type": "image",
  "markdown": "<!-- Result 1 -->..."
}
Error response

Example:

{
  "success": false,
  "error": "PDF contains 600 pages, but MAX_PDF_PAGES is 500."
}
Local Docker build

Build:

docker build -t paddleocr-vl-runpod .

Run:

docker run --rm \
  --gpus all \
  -p 8000:8000 \
  paddleocr-vl-runpod

The RunPod worker does not require port 8000 for normal Serverless operation. The command above is primarily useful for testing container startup and GPU detection.

GPU test

Before running the worker, verify Docker can access the GPU:

docker run --rm \
  --gpus all \
  nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 \
  nvidia-smi

You should see the NVIDIA GPU information.

GitHub Container Registry

The GitHub Actions workflow publishes the Docker image to:

ghcr.io/<github-user>/<repository>:latest

A commit-specific image is also created using the Git SHA.

GitHub Actions

Workflow:

.github/workflows/docker.yml

Triggered by:

push → main

or manually using:

workflow_dispatch

The workflow:

Checks out the repository.
Logs into GHCR.
Sets up Docker Buildx.
Generates image metadata.
Builds the Docker image.
Pushes the image to GHCR.
Uses GitHub Actions cache.
Generates provenance metadata.
Generates an SBOM.
RunPod deployment

After GitHub Actions successfully publishes the image:

GitHub
   ↓
GHCR
   ↓
RunPod Serverless

Use the GHCR image:

ghcr.io/<github-user>/<repository>:latest

Create a RunPod Serverless endpoint using the container image.

Recommended initial settings

For the first test:

PADDLEOCR_PIPELINE_VERSION=v1.6
PADDLEOCR_DEVICE=gpu

PADDLEOCR_MERGE_TABLES=true
PADDLEOCR_RELEVEL_TITLES=true
PADDLEOCR_CONCATENATE_PAGES=true

MAX_PDF_PAGES=500
MAX_DOWNLOAD_SIZE_MB=500

RETURN_JSON=true
LOG_LEVEL=INFO

Use a GPU with enough VRAM for PaddleOCR-VL 1.6.

First deployment test

Do not immediately test a 450-page PDF.

Start with:

1 image

Then:

1-page PDF

Then:

5-page PDF

Then:

10-page PDF

Only after those tests succeed should large documents be tested.

Large PDF strategy

The current implementation intentionally processes the PDF directly through:

pipeline.predict(
    input=str(pdf_path),
)

This follows the native PaddleOCR-VL PDF processing API.

For very large documents, such as:

300–500 pages

a future version can introduce:

PDF
 ↓
split into batches
 ↓
PaddleOCR-VL
 ↓
save intermediate results
 ↓
merge Markdown
 ↓
merge JSON

This would make the worker more suitable for very large RAG ingestion jobs.

RAG workflow

The intended architecture is:

Scanned PDF
      │
      ▼
RunPod Serverless
      │
      ▼
PaddleOCR-VL 1.6
      │
      ├──────────────┐
      ▼              ▼
   Markdown         JSON
      │              │
      └──────┬───────┘
             ▼
       Open Notebook
             │
             ▼
           RAG
             │
             ▼
       Question / Answer

Markdown is intended to preserve document structure such as:

headings
paragraphs
tables
lists
document layout information

Structured JSON can be used when downstream processing needs more detailed document information.

Security considerations

The worker currently provides several basic protections:

HTTP/HTTPS-only URLs
streamed downloads
download size limit
PDF validation
image validation
PDF page limit
isolated temporary directory per job
cleanup after each job

The worker should still be deployed behind RunPod authentication and should not be treated as an unrestricted public file-fetching service.

Model cache

The first worker startup may take longer because PaddleOCR/PaddleX may need to download model files.

Subsequent startup behavior depends on the persistence of the container/cache storage provided by the deployment environment.

Future improvements

Planned improvements:

Large-PDF batching
Persistent model cache
Object storage output
Result files instead of returning huge JSON responses
Webhook/callback support
Page-range processing
Retry handling
Job progress reporting
vLLM backend
SGLang backend
Open Notebook integration
Direct document ingestion pipeline
Backend strategy

Initial backend:

PaddleOCR-VL native

This is intentional.

The first goal is to make the complete pipeline reliable:

RunPod
 ↓
PaddleOCR-VL
 ↓
OCR
 ↓
document parsing
 ↓
Markdown / JSON

After that is stable, the inference backend can be optimized with:

vLLM

or:

SGLang

without redesigning the external RunPod API.

License

This project is intended to use the PaddleOCR-VL 1.6 model and PaddleOCR ecosystem.

Check the upstream PaddleOCR/PaddleOCR-VL licenses and terms before redistributing the model or deploying it commercially.