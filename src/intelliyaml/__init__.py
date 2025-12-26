"""Top-level package for IntelliYaml."""
from .intelliyaml import YmlEnvLoader as YmlEnvLoader
from .decorators import yamldataclass as yamldataclass

__author__ = """Nicholas Corbin"""
__email__ = 'nickcorbin17@yahoo.com'

__all__ = [
    "YmlEnvLoader",
    "yamldataclass",
]
