from __future__ import annotations

# from io import TextIOWrapper
import json
from logging import Logger
import re
from abc import ABC, abstractmethod
from functools import partial, singledispatchmethod
from os import getenv
from pathlib import Path
from typing import Any, ClassVar, Hashable, Self, overload

from dotenv import load_dotenv
from rich.console import Console
from rich.pretty import pprint
from yaml import (
    Dumper,
    FullLoader,
    MappingNode,
    ScalarNode,
    UnsafeLoader,
    YAMLObject,
    YAMLObjectMetaclass,
    load
)


load_dotenv()  # Load environment variables from a .env file if present
console = Console()
pp = partial(pprint, console=console)


class YAMLObjectABCMeta(YAMLObjectMetaclass, type(ABC)):
    """Combined metaclass for YAMLObject + ABC support."""

    def __init__(cls, name, bases, kwds):
        super().__init__(name, bases, kwds)


class BaseYmlLoader(YAMLObject, ABC, metaclass=YAMLObjectABCMeta):
    """YAML loader that expands environment variables in the form ${VAR} or ${VAR:-default}"""

    yaml_loader: ClassVar[type[FullLoader]] = FullLoader
    yaml_dumper: ClassVar[type[Dumper]] = Dumper

    default_config_file: ClassVar[Path] = Path(
        # "/Users/nicholascorbin/CodeProjects/intelliyaml/src/intelliyaml/test_logging_config.yaml"
        "/Users/nicholascorbin/CodeProjects/intelliyaml/src/intelliyaml/test_env.yaml"
    )
    _registry: ClassVar[dict[str, BaseYmlLoader]] = {}

    def __init__(self, config_file: Path | None = None, **kwargs) -> None:
        super().__init__()
        self._log = None
        self.config_file = config_file or self.default_config_file

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.data: dict[str, Any] = {}
        self.env_loader: YmlEnvLoader = self.__class__._registry.get("YmlEnvLoader")
        self.py_parser: YmlPyLoader = self.__class__._registry.get("YmlPyLoader")

        # Only log if not during class definition (avoid circular import)
        if kwargs.get("from_init_subclass") is False:
            self.logger.debug({k: getattr(self, k) for k in dir(self)})

    def __init_subclass__(cls) -> None:
        # cls._registry[cls.__name__] = super().__new__(cls)
        cls._registry[cls.__name__] = cls(from_init_subclass=True)

    @property
    def logger(self) -> Logger:
        if self._log is None:
            import intellilog._internals

            self._log = intellilog._internals.get_internal_logger("intelliyaml")
        return self._log

    @classmethod
    @abstractmethod
    @overload
    def from_yaml(cls, loader: FullLoader, node: MappingNode) -> dict[Hashable, Any]: ...
    @classmethod
    @abstractmethod
    @overload
    def from_yaml(cls, loader: FullLoader, node: ScalarNode) -> str: ...
    @classmethod
    @abstractmethod
    def from_yaml(cls, loader: FullLoader, node):
        """YAML constructor to expand environment variables."""
        raise NotImplementedError(
            "BaseYmlLoader.from_yaml must be implemented in subclasses."
        )

    @classmethod
    @abstractmethod
    @overload
    def to_yaml(cls, dumper: Dumper, data: dict[str, Any]) -> MappingNode: ...
    @classmethod
    @abstractmethod
    @overload
    def to_yaml(cls, dumper: Dumper, data: str) -> ScalarNode: ...
    @classmethod
    @abstractmethod
    def to_yaml(cls, dumper: Dumper, data):
        """YAML representer to dump environment variables."""
        raise NotImplementedError(
            "BaseYmlLoader.to_yaml must be implemented in subclasses."
        )

    def read_config(self) -> None:
        print(f"Reading config from {self.config_file}...")
        try:
            self.data = self.env_loader.expand_env_vars(
                load(stream=self._stream, Loader=self.yaml_loader)
            )
        finally:
            if self._stream.closed is False:
                self._stream.close()

    def __enter__(self) -> Self:
        self._stream = self.config_file.open("r")
        self.read_config()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._stream.close()

    def load_yaml(self, data: str | None = None) -> dict[str, Any]:
        return self.yaml_loader(data or self.json_str()).get_data()

    def json_str(self, data: dict[str, Any] | None = None) -> str:
        return json.dumps(data or self.data, indent=2)

    def json_dict(self, data: str | None = None) -> dict[str, Any]:
        return json.loads(data or self.json_str())

    def replace(self, values: dict[str, str]) -> dict[str, Any]:
        """Expand env vars in a list of strings."""
        if not self.data:
            raise RuntimeError(
                "This method requires loaded data. Use 'with' statement or call read_config() first."
            )

        text = self.json_str(self.data)
        for key, value in values.items():
            text = text.replace(f"{{{key}}}", value)
        return self.json_dict(text)

    def backup_config(self, backup_file: Path | None = None) -> None:
        """Backup the current configuration to a specified path."""

        backup_path = backup_file or self.config_file.with_suffix(".backup.json")
        with backup_path.open("w") as backup:
            backup.write(self.json_str())


class YmlEnvLoader(BaseYmlLoader):
    yaml_tag: ClassVar[str] = "!env"
    env_var_pattern: ClassVar[re.Pattern] = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, config_file: Path | None = None, **kwargs) -> None:
        super().__init__(config_file=config_file, **kwargs)

        # Register the implicit resolver for environment variable patterns
        self.yaml_loader.add_implicit_resolver(
            tag=self.yaml_tag,
            regexp=self.env_var_pattern,
            first=None
        )

    @classmethod
    def from_yaml(cls, loader: FullLoader, node: ScalarNode) -> str:
        print(f"{cls.__name__}.from_yaml called...")
        value: str = loader.construct_scalar(node=node)
        return cls.expand_string(value)

    @classmethod
    def to_yaml(cls, dumper: Dumper, data: str) -> ScalarNode:
        return dumper.represent_scalar(tag=cls.yaml_tag, value=data)

    @classmethod
    def expand_string(cls, value: str) -> str:
        """Expand ${VAR} or ${VAR:-default} patterns in a string."""
        pattern = cls.env_var_pattern

        def regex_replacer(match: re.Match[str]) -> str:
            env_var = match.group(1)
            if ":-" in env_var:
                var_name, default = env_var.split(":-", 1)
                return getenv(key=var_name, default=default)
            return getenv(key=env_var, default=match.group(0))

        return pattern.sub(regex_replacer, value)

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

    @expand_env_vars.register(Path)
    def _(self, data: Path) -> Path:
        """Expand env vars in Path and resolve to absolute."""
        expanded = self.expand_string(str(data))
        return Path(expanded).resolve()


class YmlPyLoader(BaseYmlLoader):
    """YAML loader with methods to return formatted data based on the provided arguments."""

    yaml_tag: ClassVar[str] = "!!python/object/attr"
    yaml_loader: ClassVar[type[UnsafeLoader]] = UnsafeLoader

    def __init__(self, config_file: Path | None = None, **kwargs) -> None:
        super().__init__(config_file=config_file, **kwargs)
        pp(self.yaml_loader.yaml_constructors)
        pp(self.yaml_loader.yaml_multi_constructors)
        exit()

    @classmethod
    def from_yaml(cls, loader: UnsafeLoader, suffix, node: ScalarNode) -> str:
        print(f"{cls.__name__}.from_yaml called...")
        print(
              f"{node.id=} | {node.tag=} | {node.style=}"
              f"{node.start_mark=} | {node.end_mark=} | {node.value=}"
        )
        name = loader.construct_scalar(node=node)
        obj = loader.find_python_name(name, node.start_mark)
        print(f"{name=} ... {obj=}")
        exit()
        value = getattr(obj,)
        return value

    @classmethod
    def to_yaml(cls, dumper: Dumper, data: str) -> ScalarNode:
        return dumper.represent_scalar(tag=cls.yaml_tag, value=data)


def main() -> None:
    with YmlEnvLoader() as yml:
        env_config = yml.data

    pp(env_config)

    with YmlPyLoader(
        Path(
            "/Users/nicholascorbin/CodeProjects/intelliyaml/src/intelliyaml/test_logging_config.yaml"
        )
    ) as ymlp:
        parsed_config = ymlp.data

    pp(parsed_config)


if __name__ == "__main__":
    main()
