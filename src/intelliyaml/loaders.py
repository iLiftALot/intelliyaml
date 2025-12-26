from __future__ import annotations

from yaml import FullLoader, ScalarNode,load
from typing import Any, ClassVar, Self
from pathlib import Path
from io import IOBase
import re
from os import getenv
from functools import singledispatchmethod

class YmlLoader(FullLoader):
    config_path: Path
    env_var_pattern: ClassVar[re.Pattern[str]] = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, stream: IOBase | None) -> None:
        # > SafeLoader.__init__ consumes the stream, so we need a fresh handle for read_config()
        self._stream = stream or self.__class__.config_path.open("r")
        super().__init__(self._stream)
        self._stream.seek(0)  # > Reset stream position after SafeLoader consumes it

        self.data: dict[str, Any] = {}

        self.add_implicit_resolver(
            tag="!env",
            regexp=self.env_var_pattern,
            first=None,  # > first=None means check all characters
        )
        self.add_constructor(tag="!env", constructor=self.env_var_constructor)

    @classmethod
    def ini(cls, config_path: Path) -> Self:
        cls.config_path = config_path
        return cls(stream=None)

    @staticmethod
    def env_var_constructor(loader: YmlLoader, node: ScalarNode) -> str:
        """Expand environment variables in the form ${VAR} or ${VAR:-default}"""
        value: str = loader.construct_scalar(node=node)
        return loader.expand_string(value=value)

    def expand_string(self, value: str) -> str:
        """Expand ${VAR} or ${VAR:-default} patterns in a string."""
        pattern = self.env_var_pattern

        def replacer(match: re.Match[str]) -> str:
            env_var = match.group(1)
            if ":-" in env_var:
                var_name, default = env_var.split(":-", 1)
                return getenv(key=var_name, default=default)
            return getenv(key=env_var, default=match.group(0))

        return pattern.sub(replacer, value)

    @singledispatchmethod
    def expand_env_vars(self, data: Any) -> Any:
        """Recursively expand env vars in all string values."""
        return data

    @expand_env_vars.register(str)
    def _(self, data: str) -> str:
        return self.expand_string(data)

    @expand_env_vars.register(dict)
    def _(self, data: dict[str, Any]) -> dict[str, Any]:
        return {k: self.expand_env_vars(v) for k, v in data.items()}

    @expand_env_vars.register(list)
    def _(self, data: list[Any]) -> list[Any]:
        return [self.expand_env_vars(item) for item in data]

    def read_config(self) -> None:
        try:
            self.data = self.expand_env_vars(
                load(stream=self._stream, Loader=self.__class__)
            )
        finally:
            if self._stream.closed is False:
                self._stream.close()

    def __enter__(self) -> dict[str, Any]:
        self.read_config()
        return self.data

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stream.close()
