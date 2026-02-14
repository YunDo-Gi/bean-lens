"""bean-lens: Extract structured coffee bean info from package or card images."""

from bean_lens.core import extract
from bean_lens.schema import BeanInfo, Origin

__version__ = "0.1.0"

__all__ = ["extract", "BeanInfo", "Origin", "__version__"]
