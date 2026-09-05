Siap. Ini **File #9 — `README.md`**. Saya buat README yang sekaligus menjadi dokumentasi cara menjalankan worker, format input RunPod, konfigurasi environment, dan deployment GHCR.

Letakkan di **root repository**, sejajar dengan `Dockerfile`.

````markdown
# PaddleOCR-VL 1.6 — RunPod Serverless

RunPod Serverless worker untuk menjalankan **PaddleOCR-VL 1.6** dari Hugging Face.

Worker ini dirancang untuk memproses:

- Image
- PDF
- PDF multi-page
- Dokumen hasil scan
- OCR + document parsing
- Output Markdown
- Output JSON

Hasil Markdown dapat digunakan sebagai input untuk sistem RAG seperti Open Notebook.

---

## Architecture

```text
                    ┌─────────────────────┐
                    │      RunPod         │
                    │     Serverless      │
                    └──────────┬──────────┘
                               │
                               │ Job
                               ▼
                    ┌─────────────────────┐
                    │   PaddleOCR-VL 1.6  │
                    │                     │
                    │ PaddleOCR Pipeline  │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
                ▼                             ▼
             Markdown                       JSON
                │                             │
                └──────────────┬──────────────┘
                               │
                               ▼
                         RAG / Open Notebook
````

---

# Project Structure

```text
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
```

---

# PaddleOCR-VL Model

Model yang digunakan:

```text
PaddlePaddle/PaddleOCR-VL-1.6
```

Model version:

```text
PaddleOCR-VL-1.6-0.9B
```

Pipeline version:

```text
v1.6
```

---

# Requirements

Worker menggunakan:

* NVIDIA CUDA 12.6
* PaddlePaddle GPU 3.2.1
* PaddleOCR 3.6+
* Python 3
* RunPod Serverless
* PyMuPDF
* Pillow

GPU yang digunakan harus kompatibel dengan CUDA/PaddlePaddle.

Untuk performa yang baik, gunakan GPU dengan VRAM yang memadai untuk seluruh pipeline PaddleOCR-VL.

---

# Local Docker Build

Build image:

```bash
docker build -t paddleocr-vl-runpod .
```

Run container:

```bash
docker run --rm \
  --gpus all \
  -e PADDLEOCR_DEVICE=gpu \
  paddleocr-vl-runpod
```

Container akan menjalankan RunPod Serverless worker.

---

# Environment Variables

Semua konfigurasi utama dapat diubah melalui environment variable.

## PaddleOCR

### `PADDLEOCR_PIPELINE_VERSION`

Default:

```text
v1.6
```

Contoh:

```bash
-e PADDLEOCR_PIPELINE_VERSION=v1.6
```

---

### `PADDLEOCR_DEVICE`

Default:

```text
gpu
```

Contoh:

```bash
-e PADDLEOCR_DEVICE=gpu
```

Untuk CPU:

```bash
-e PADDLEOCR_DEVICE=cpu
```

CPU tidak direkomendasikan untuk production inference.

---

# PDF Configuration

## `MAX_PDF_PAGES`

Default:

```text
0
```

Artinya tidak ada batas jumlah halaman.

Contoh:

```bash
-e MAX_PDF_PAGES=10
```

Hanya memproses maksimal 10 halaman.

---

# Output

## `OUTPUT_FORMAT`

Default:

```text
markdown
```

---

## `RETURN_JSON`

Default:

```text
true
```

Jika:

```text
true
```

worker akan mengembalikan Markdown dan JSON.

Jika:

```text
false
```

worker hanya mengembalikan Markdown.

---

# Temporary Storage

## `TEMP_DIR`

Default:

```text
/tmp/paddleocr
```

---

## Hugging Face Cache

## `HF_HOME`

Default:

```text
/tmp/huggingface
```

---

## Paddle Cache

## `PADDLE_HOME`

Default:

```text
/tmp/paddle
```

---

# RunPod Input

Worker menerima dua jenis input:

```text
image_url
```

atau:

```text
pdf_url
```

Tidak boleh mengirim keduanya sekaligus.

---

# Image Example

Input:

```json
{
  "input": {
    "image_url": "https://example.com/document.png"
  }
}
```

Worker akan:

```text
Download image
      ↓
PaddleOCR-VL
      ↓
Markdown + JSON
```

---

# PDF Example

Input:

```json
{
  "input": {
    "pdf_url": "https://example.com/document.pdf"
  }
}
```

Worker akan:

```text
Download PDF
      ↓
Render PDF page
      ↓
Page image
      ↓
PaddleOCR-VL
      ↓
Next page
      ↓
...
      ↓
Markdown + JSON
```

---

# Example Response

Contoh response:

```json
{
  "success": true,
  "type": "pdf",
  "pages": 3,
  "markdown": "<!-- Page 1 -->\n\n# Judul Dokumen\n\n...",
  "results": [
    {
      "page": 1,
      "results": []
    }
  ]
}
```

Struktur JSON aktual dapat berbeda tergantung versi PaddleOCR/PaddleX yang digunakan.

---

# Markdown Output

Markdown digunakan sebagai format utama untuk RAG.

Contoh:

```markdown
<!-- Page 1 -->

# Judul Dokumen

Isi dokumen...

## Bab 1

Materi pembelajaran...

<!-- Page 2 -->

Tabel:

| No | Nama | Nilai |
|---|---|---|
| 1 | A | 90 |
| 2 | B | 85 |
```

Format ini dapat diteruskan ke sistem seperti:

```text
PaddleOCR-VL
      ↓
Markdown
      ↓
Open Notebook
      ↓
Embedding
      ↓
Vector Database
      ↓
RAG
```

---

# GitHub Container Registry

GitHub Actions akan otomatis membuat Docker image dan push ke:

```text
ghcr.io/<github-user>/<repository>
```

Contoh:

```text
ghcr.io/karem505/paddleocr-vl-runpod
```

Workflow:

```text
git push
   ↓
GitHub Actions
   ↓
Docker Build
   ↓
GHCR
```

---

# Docker Image Tags

Setiap build menghasilkan:

```text
latest
```

dan tag berdasarkan commit SHA:

```text
sha-xxxxxxxx
```

Contoh:

```text
ghcr.io/karem505/paddleocr-vl-runpod:latest
```

atau:

```text
ghcr.io/karem505/paddleocr-vl-runpod:sha-a1b2c3d
```

Untuk RunPod, gunakan:

```text
ghcr.io/karem505/paddleocr-vl-runpod:latest
```

---

# RunPod Deployment

Setelah image tersedia di GHCR:

```text
RunPod
   ↓
Serverless
   ↓
New Endpoint
   ↓
Custom Docker Image
```

Docker image:

```text
ghcr.io/<github-user>/<repository>:latest
```

Pilih GPU yang kompatibel.

Worker tidak membutuhkan HTTP server manual.

RunPod Serverless akan berkomunikasi dengan:

```python
runpod.serverless.start(
    {
        "handler": handler
    }
)
```

---

# Model Download

Model PaddleOCR-VL akan di-download secara otomatis ketika pipeline pertama kali dijalankan jika model belum tersedia di cache.

Karena itu:

```text
Container startup
       ↓
PaddleOCR initialization
       ↓
Download model
       ↓
Load model
       ↓
Worker ready
```

Cold start pertama dapat lebih lama dibandingkan job berikutnya.

---

# Recommended Production Flow

Untuk dokumen besar:

```text
PDF
 │
 ▼
RunPod Serverless
 │
 ▼
PDF → Pages
 │
 ▼
PaddleOCR-VL 1.6
 │
 ├── OCR
 ├── Layout
 ├── Tables
 └── Document parsing
 │
 ▼
Markdown
 │
 ▼
Open Notebook
 │
 ▼
Embedding
 │
 ▼
RAG
```

---

# Large PDF

Worker dapat menerima PDF multi-page.

Contoh:

```text
450 pages
```

akan diproses:

```text
Page 1
Page 2
Page 3
...
Page 450
```

Secara berurutan.

Untuk dokumen yang sangat besar, disarankan menggunakan batching/chunking sehingga satu RunPod job tidak terlalu besar.

---

# Development Roadmap

## Phase 1 — Basic Worker

```text
GitHub
  ↓
GHCR
  ↓
RunPod
  ↓
PaddleOCR-VL
```

## Phase 2 — PDF Optimization

Menambahkan:

* configurable DPI
* streaming page processing
* page batching
* memory optimization
* automatic cleanup

## Phase 3 — Storage

Output dapat disimpan ke object storage:

```text
RunPod
  ↓
OCR
  ↓
Markdown / JSON
  ↓
Object Storage
```

## Phase 4 — Open Notebook Integration

```text
PDF
 ↓
RunPod OCR
 ↓
Markdown
 ↓
Open Notebook
 ↓
RAG
```

---

# Important

Versi pertama worker menggunakan **native PaddleOCR-VL backend**.

vLLM belum digunakan.

Tujuannya adalah memastikan terlebih dahulu bahwa:

```text
PaddleOCR-VL 1.6
+
PaddlePaddle GPU
+
RunPod Serverless
+
PDF processing
```

berjalan dengan benar.

Setelah pipeline dasar stabil, backend inference dapat dioptimalkan menggunakan vLLM/SGLang jika diperlukan.

---

# License

Refer to the licenses of:

* PaddleOCR
* PaddlePaddle
* PaddleOCR-VL
* Hugging Face model
* Third-party dependencies

Check the individual project/model licenses before commercial deployment.
