"""
Pytest configuration - sets up vendored package imports.
"""

import sys
from pathlib import Path

# Add project root to path so _vendor can be imported
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import _vendor to set up vendored package paths
import _vendor  # noqa: F401, E402
