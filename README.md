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
  Roast Date:    2024.01.15
  Altitude:      1,800-2,000m
```

JSON output:
```bash
bean-lens image.jpg --json
```

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
| `roast_date` | Roast date |
| `altitude` | Growing altitude |

## License

MIT
