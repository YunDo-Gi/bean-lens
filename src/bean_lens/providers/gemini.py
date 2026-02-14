"""Gemini provider implementation."""

import os
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from bean_lens.exceptions import AuthenticationError, ImageError, RateLimitError
from bean_lens.providers.base import BaseProvider, ImageInput
from bean_lens.schema import BeanInfo

EXTRACTION_PROMPT = """Analyze this coffee bean package or card image and extract the following information.
Return a JSON object with these fields (use null for missing information):

{
  "roastery": "Name of the roastery/brand",
  "name": "Name of the coffee bean",
  "origin": {
    "country": "Country of origin",
    "region": "Region within the country",
    "farm": "Farm or washing station name"
  },
  "variety": ["List of coffee varieties, e.g., Geisha, Typica, SL28"],
  "process": "Processing method (e.g., Washed, Natural, Honey)",
  "roast_level": "Roast level (e.g., Light, Medium, Dark)",
  "flavor_notes": ["List of flavor notes, e.g., Citrus, Jasmine, Chocolate"],
  "roast_date": "Roast date if visible",
  "altitude": "Growing altitude (e.g., 1800-2000m)"
}

Important:
- Extract text in its original language (Korean, English, etc.)
- Only include information clearly visible in the image
- Return valid JSON only, no additional text"""


class GeminiProvider(BaseProvider):
    """Gemini Vision API provider."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash"):
        """Initialize Gemini provider.

        Args:
            api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
            model: Model name to use.

        Raises:
            AuthenticationError: If no API key is provided or found.
        """
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise AuthenticationError(
                "No API key provided. Set GEMINI_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.model = model
        self.client = genai.Client(api_key=self.api_key)

    def _load_image(self, image: ImageInput) -> Image.Image:
        """Load image from various input types."""
        if isinstance(image, Image.Image):
            return image

        path = Path(image) if isinstance(image, str) else image
        if not path.exists():
            raise ImageError(f"Image file not found: {path}")

        try:
            return Image.open(path)
        except Exception as e:
            raise ImageError(f"Failed to open image: {e}") from e

    def extract(self, image: ImageInput) -> BeanInfo:
        """Extract bean info from an image using Gemini Vision.

        Args:
            image: Image input (file path, Path object, or PIL Image)

        Returns:
            BeanInfo with extracted information

        Raises:
            ImageError: If image cannot be loaded
            RateLimitError: If API rate limit is exceeded
            AuthenticationError: If API key is invalid
        """
        pil_image = self._load_image(image)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[pil_image, EXTRACTION_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=BeanInfo,
                ),
            )
            return BeanInfo.model_validate_json(response.text)

        except genai.errors.ClientError as e:
            if "rate" in str(e).lower() or "quota" in str(e).lower():
                raise RateLimitError(f"API rate limit exceeded: {e}") from e
            if "auth" in str(e).lower() or "key" in str(e).lower():
                raise AuthenticationError(f"Invalid API key: {e}") from e
            raise
        except Exception as e:
            raise ImageError(f"Failed to extract info: {e}") from e
