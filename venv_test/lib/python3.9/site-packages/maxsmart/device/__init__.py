# maxsmart/device/__init__.py

# Export the main MaxSmartDevice class to maintain API compatibility
from .core import MaxSmartDevice
from .polling import AdaptivePollingMixin, PollingMode

__all__ = ['MaxSmartDevice', 'AdaptivePollingMixin', 'PollingMode']