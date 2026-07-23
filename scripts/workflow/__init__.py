"""Version 0.1 orchestration and canonical-result support.

The modules in this package adapt the verified pilot implementation. They do
not replace the scientific Part B--E methods.
"""

from .models import CANONICAL_SCHEMA_VERSION, PROCESSING_VERSION

__all__ = ["CANONICAL_SCHEMA_VERSION", "PROCESSING_VERSION"]
