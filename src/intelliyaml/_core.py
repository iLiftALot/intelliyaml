from __future__ import annotations

from pathlib import Path
from os import getenv
from functools import partial
from typing import overload

from dotenv import load_dotenv, dotenv_values
from rich.console import Console
from rich.pretty import pprint
from intellipath import ProjectPath

# Package-level paths (no external deps)
PACKAGE_ENV_FILE = ProjectPath.ENV
PACKAGE_DIR = ProjectPath.PACKAGE

# Load package-local environment first
# Use override=False so project-level .env can override if needed
if PACKAGE_ENV_FILE.exists():
    load_dotenv(PACKAGE_ENV_FILE, override=False)

# Package-isolated env values (doesn't pollute os.environ)
_package_env: dict[str, str | None] = dotenv_values(PACKAGE_ENV_FILE) if PACKAGE_ENV_FILE.exists() else {}


@overload
def get_package_env(key: str, default: str) -> str: ...
@overload
def get_package_env(key: str, default: None = None) -> str | None: ...
def get_package_env(key: str, default: str | None = None) -> str | None:
    """Get environment variable, checking package .env first, then system env."""
    return _package_env.get(key) or getenv(key, default)


# Console for this package (independent instance)
console = Console()
pp = partial(pprint, console=console, expand_all=True)


class IntelliYamlConfig:
    """Package configuration - no external deps."""
    
    DEBUG: bool = get_package_env("INTELLIYAML_DEBUG", "false").lower() == "true"
    DEFAULT_CONFIG_PATH: Path = PACKAGE_DIR / "test_env.yaml"
    
    @classmethod
    def reload(cls) -> None:
        """Reload configuration from environment."""
        global _package_env
        _package_env = dotenv_values(PACKAGE_ENV_FILE) if PACKAGE_ENV_FILE.exists() else {}
        cls.DEBUG = get_package_env("INTELLIYAML_DEBUG", "false").lower() == "true"
