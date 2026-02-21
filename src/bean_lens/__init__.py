"""bean-lens: Extract structured coffee bean info from package or card images."""

from bean_lens.core import extract
from bean_lens.normalization import NormalizedBeanInfo, normalize_bean_info
from bean_lens.schema import BeanInfo, Origin

__version__ = "0.1.0"

__all__ = [
    "extract",
    "normalize_bean_info",
    "BeanInfo",
    "NormalizedBeanInfo",
    "Origin",
    "__version__",
]
