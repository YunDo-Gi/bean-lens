from io import BytesIO
import os
from pathlib import Path
import sys

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

# Ensure local src package is importable in serverless runtime.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bean_lens import extract  # noqa: E402
from bean_lens.exceptions import AuthenticationError, ImageError, RateLimitError  # noqa: E402
from bean_lens.schema import BeanInfo  # noqa: E402

app = FastAPI(title="bean-lens API", version="1.0.0")

raw_origins = os.getenv("FRONTEND_ORIGINS", "*")
allow_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/extract", response_model=BeanInfo)
async def extract_bean_info(image: UploadFile = File(...)) -> BeanInfo:
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="image file is required")

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        pil_image = Image.open(BytesIO(payload))
        return extract(pil_image)
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="invalid image format") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")
