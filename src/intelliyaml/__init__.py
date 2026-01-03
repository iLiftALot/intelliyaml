"""Top-level package for IntelliYaml."""
from pkg_registry import init_vendor
init_vendor()  # Auto-finds and adds _vendor to sys.path

from .main import (
    YmlPyObject as YmlPyObject
)
from .decorators import yamldataclass as yamldataclass

__package__ = "intelliyaml"
__author__ = """Nicholas Corbin"""
__email__ = 'nickcorbin17@yahoo.com'

__all__ = [
    "YmlPyObject",
    "yamldataclass"
]
