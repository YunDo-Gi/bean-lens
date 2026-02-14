"""Core extraction function."""

from pathlib import Path

from PIL import Image

from bean_lens.providers.gemini import GeminiProvider
from bean_lens.schema import BeanInfo

ImageInput = str | Path | Image.Image


def extract(image: ImageInput, *, api_key: str | None = None) -> BeanInfo:
    """Extract coffee bean information from a package or card image.

    Args:
        image: Image input - file path (str), Path object, or PIL Image
        api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.

    Returns:
        BeanInfo with extracted information. Fields will be None if not found.

    Raises:
        AuthenticationError: If no API key is provided or invalid
        ImageError: If image cannot be loaded
        RateLimitError: If API rate limit is exceeded

    Example:
        >>> from bean_lens import extract
        >>> result = extract("my_coffee.jpg")
        >>> print(result.origin.country)
        에티오피아
        >>> print(result.flavor_notes)
        ['자몽', '재스민', '흑설탕']
    """
    provider = GeminiProvider(api_key=api_key)
    return provider.extract(image)
