import base64
from io import BytesIO
import os
from pathlib import Path
import sys

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

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
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP"}

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


class ExtractRequest(BaseModel):
    imageBase64: str


def _validate_payload_size(payload: bytes) -> None:
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image too large")


def _validate_multipart_content_type(content_type: str | None) -> None:
    if not content_type:
        raise HTTPException(status_code=400, detail="image file is required")
    normalized = content_type.split(";")[0].strip().lower()
    if normalized not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="unsupported image content type")


def _decode_base64_image(image_base64: str) -> bytes:
    value = image_base64.strip()
    if not value:
        raise HTTPException(status_code=400, detail="imageBase64 is required")

    # Support data URL format: data:image/jpeg;base64,<payload>
    if value.startswith("data:"):
        _, sep, value = value.partition(",")
        if not sep:
            raise HTTPException(status_code=400, detail="invalid imageBase64 data URL")

    try:
        payload = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid imageBase64 encoding") from exc

    if not payload:
        raise HTTPException(status_code=400, detail="empty file")
    _validate_payload_size(payload)

    return payload


@app.post("/extract", response_model=BeanInfo)
async def extract_bean_info(request: Request, image: UploadFile | None = File(default=None)) -> BeanInfo:
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("application/json"):
        try:
            body = ExtractRequest.model_validate(await request.json())
        except Exception as exc:
            raise HTTPException(status_code=400, detail="imageBase64 is required in JSON body") from exc
        payload = _decode_base64_image(body.imageBase64)
    else:
        if image is None:
            raise HTTPException(status_code=400, detail="image file is required")
        _validate_multipart_content_type(image.content_type)
        payload = await image.read()
        if not payload:
            raise HTTPException(status_code=400, detail="empty file")
        _validate_payload_size(payload)

    try:
        pil_image = Image.open(BytesIO(payload))
        if (pil_image.format or "").upper() not in ALLOWED_PIL_FORMATS:
            raise HTTPException(status_code=400, detail="unsupported image format")
        return extract(pil_image)
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="invalid image format") from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")
