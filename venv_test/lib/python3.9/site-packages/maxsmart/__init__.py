# maxsmart/__init__.py

__version__ = "2.0.5"

from .device import MaxSmartDevice
from .discovery import MaxSmartDiscovery

# Backward compatibility aliases
from .discovery import MaxSmartDiscovery as Discovery

__all__ = ['MaxSmartDevice', 'MaxSmartDiscovery', 'Discovery']