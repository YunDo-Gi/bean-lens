# bean-lens

Extract structured coffee bean info from package or card images using Vision LLM or OCR.

## Installation

```bash
pip install bean-lens
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add bean-lens
```

## Setup

Default provider is Gemini Vision:

```bash
export GEMINI_API_KEY=your-api-key
```

To use Google Vision OCR instead:

```bash
export BEAN_LENS_PROVIDER=ocr
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GEMINI_API_KEY=your-api-key  # for OCR text -> LLM structuring
export OCR_TEXT_LLM_ENABLED=true
export OCR_TEXT_LLM_MODEL=gemini-2.5-flash-lite
```

For serverless environments, you can pass credentials as JSON:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON='{"type":"service_account", ... }'
```

## Usage

### Python

```python
from bean_lens import extract

result = extract("coffee_package.jpg")

print(result.roastery)        # "Fritz Coffee"
print(result.origin.country)  # "Ethiopia"
print(result.flavor_notes)    # ["Citrus", "Jasmine", "Honey"]
```

### CLI

```bash
bean-lens image.jpg
```

Output:
```
  bean-lens

  Roastery:      Fritz Coffee
  Name:          Ethiopia Yirgacheffe
  Origin:        Ethiopia / Yirgacheffe / Konga
  Variety:       Heirloom
  Process:       Washed
  Roast Level:   Light
  Flavor Notes:  Citrus, Jasmine, Honey
  Altitude:      1,800-2,000m
```

JSON output:
```bash
bean-lens image.jpg --json
```

### Normalization (v1)

You can normalize extracted fields into canonical dictionary keys:

```python
from bean_lens import extract, normalize_bean_info

bean = extract("coffee_package.jpg")
normalized = normalize_bean_info(bean, dictionary_version="v1")

print(normalized.process.normalized_key)  # washed
print(normalized.country.normalized_key)  # ET
```

## API (FastAPI + Vercel)

This repository can be deployed as a Python API on Vercel.

### Endpoints

- `GET /health`: health check
- `POST /extract`: supports both
  - `multipart/form-data` (`image` file field)
  - `application/json` (`imageBase64` string, raw base64 or Data URL)
  - response:
    - `normalized`: `NormalizedBeanInfo`
    - `metadata.parser`: extraction parser path (`gemini_vision`, `ocr_text_llm`, `heuristic_fallback`, `ocr_heuristic`)

### Local API run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set provider environment variables:

```bash
export GEMINI_API_KEY=your-api-key
export BEAN_LENS_PROVIDER=gemini  # or ocr
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json  # for ocr
```

Optional CORS origins (comma-separated):

```bash
export FRONTEND_ORIGINS=http://localhost:5173,https://your-frontend-domain.com
```

Optional upload limit (bytes, default: 8388608 = 8MB):

```bash
export MAX_IMAGE_BYTES=8388608
```

Optional normalization settings:

```bash
export DICTIONARY_VERSION=v1
export UNKNOWN_QUEUE_PATH=/tmp/bean-lens-unknown.jsonl
export UNKNOWN_QUEUE_MIN_CONFIDENCE=0.85
export UNKNOWN_QUEUE_WEBHOOK_URL=https://your-endpoint.example.com/unknown-queue
export UNKNOWN_QUEUE_WEBHOOK_TIMEOUT_SEC=2.0
export UNKNOWN_QUEUE_WEBHOOK_TOKEN=your-shared-token
```

3. Run FastAPI locally:

```bash
uvicorn api.index:app --reload --port 8000
```

4. Test:

```bash
curl http://localhost:8000/health
```

```bash
curl -X POST "http://localhost:8000/extract" \
  -F "image=@coffee_package.jpg"
```

```bash
curl -X POST "http://localhost:8000/extract" \
  -H "Content-Type: application/json" \
  -d '{"imageBase64":"<base64-encoded-image>"}'
```

Allowed upload MIME types (multipart): `image/jpeg`, `image/jpg`, `image/png`, `image/webp`

### Vercel deployment

1. Import this repository in Vercel.
2. Add environment variable:
   - `GEMINI_API_KEY`
   - `BEAN_LENS_PROVIDER` (`gemini` or `ocr`)
   - `GOOGLE_APPLICATION_CREDENTIALS_JSON` (when `BEAN_LENS_PROVIDER=ocr`)
   - `FRONTEND_ORIGINS` (example: `https://your-frontend-domain.com`)
3. Deploy. (Configuration is already defined in `vercel.json`.)
4. Verify:
   - `https://<your-vercel-domain>/health`
   - `POST https://<your-vercel-domain>/extract`

## Extracted Fields

| Field | Description |
|-------|-------------|
| `roastery` | Roastery or brand name |
| `name` | Coffee bean name |
| `origin` | Origin info (country, region, farm) |
| `variety` | Coffee varieties (e.g., Geisha, Typica) |
| `process` | Processing method (e.g., Washed, Natural) |
| `roast_level` | Roast level (e.g., Light, Medium-Light, Medium, Medium-Dark, Dark) |
| `flavor_notes` | Flavor notes list |
| `altitude` | Growing altitude |

## License

MIT

### Beanconqueror import workflow (dictionary expansion)

To build candidate dictionary entries from Beanconqueror source:

```bash
python scripts/import_beanconqueror.py --source /path/to/Beanconqueror
```

Generated review files are written to `data/imports/beanconqueror/`:
- `roast_aliases.json`
- `flavor_terms.json`
- `flavor_aliases.json`

Review and selectively merge candidates into
`src/bean_lens/normalization/data/v1/terms.py` and
`src/bean_lens/normalization/data/v1/aliases.py`.

### Unknown queue operations

When `UNKNOWN_QUEUE_PATH` is set, unmapped (and optionally low-confidence) normalization
results are appended as JSONL records.  
When `UNKNOWN_QUEUE_WEBHOOK_URL` is set, the same records are also sent as HTTP POST JSON.

To review frequent misses:

```bash
python scripts/summarize_unknown_queue.py \
  --input /tmp/bean-lens-unknown.jsonl \
  --top 50
```

To generate alias review candidates from the queue:

```bash
python scripts/generate_alias_candidates.py \
  --input /tmp/bean-lens-unknown.jsonl \
  --output data/review/alias_candidates.json \
  --min-count 2 \
  --min-score 0.72
```

### Webhook receiver (DB sink)

This repository includes a minimal receiver server that stores unknown queue
events in PostgreSQL (Supabase-compatible).

Run receiver:

```bash
pip install -r receiver_app/requirements.txt
uvicorn receiver_app.main:app --reload --port 8100
```

Deploy on Vercel:
1. Create a new Vercel project from the same repository
2. Set `Root Directory` to `receiver_app`
3. Deploy (uses `receiver_app/api/index.py` and `receiver_app/vercel.json`)

Receiver environment variables:

```bash
export DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<db>?sslmode=require
export UNKNOWN_QUEUE_RECEIVER_TOKEN=your-shared-token
```

Then configure bean-lens API:

```bash
export UNKNOWN_QUEUE_WEBHOOK_URL=http://localhost:8100/unknown-queue
export UNKNOWN_QUEUE_WEBHOOK_TIMEOUT_SEC=2.0
export UNKNOWN_QUEUE_WEBHOOK_TOKEN=your-shared-token
```
