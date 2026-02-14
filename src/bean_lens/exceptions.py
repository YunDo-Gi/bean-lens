"""Custom exceptions for bean-lens."""


class BeanLensError(Exception):
    """Base exception for bean-lens."""

    pass


class AuthenticationError(BeanLensError):
    """Raised when API key is invalid or missing."""

    pass


class RateLimitError(BeanLensError):
    """Raised when API rate limit is exceeded."""

    pass


class ImageError(BeanLensError):
    """Raised when image cannot be read or is invalid."""

    pass
