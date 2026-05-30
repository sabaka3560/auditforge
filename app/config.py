# Compatibility shim — storage.py imports from app.config.
# The canonical location is app.core.config.
from app.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
