"""Base provider interface."""

from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

from bean_lens.schema import BeanInfo

ImageInput = str | Path | Image.Image


class BaseProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def extract(self, image: ImageInput) -> BeanInfo:
        """Extract bean info from an image.

        Args:
            image: Image input (file path, Path object, or PIL Image)

        Returns:
            BeanInfo with extracted information
        """
        pass

    def get_extraction_metadata(self) -> dict[str, str]:
        """Return provider-specific extraction metadata."""
        return {}
