# bean-lens

Extract structured coffee bean info from package or card images using Vision LLM.

## Installation

```bash
pip install bean-lens
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add bean-lens
```

## Setup

Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) and set it as an environment variable:

```bash
export GEMINI_API_KEY=your-api-key
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

### Local API run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set Gemini API key:

```bash
export GEMINI_API_KEY=your-api-key
```

Optional CORS origins (comma-separated):

```bash
export FRONTEND_ORIGINS=http://localhost:5173,https://your-frontend-domain.com
```

Optional upload limit (bytes, default: 8388608 = 8MB):

```bash
export MAX_IMAGE_BYTES=8388608
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

Allowed image formats: `JPEG`, `PNG`, `WebP`, `MPO`

### Vercel deployment

1. Import this repository in Vercel.
2. Add environment variable:
   - `GEMINI_API_KEY`
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
| `roast_level` | Roast level (e.g., Light, Medium, Dark) |
| `flavor_notes` | Flavor notes list |
| `altitude` | Growing altitude |

## License

MIT
