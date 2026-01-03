from __future__ import annotations

from io import TextIOWrapper
import json
import re
# from abc import ABC, ABCMeta, abstractmethod
from functools import singledispatchmethod
from pathlib import Path  # Use stdlib Path to avoid circular imports

# from logging import Logger
from os import getenv
import sys
from typing import Any, ClassVar, Generic, Hashable, Self, TypeVar
from yaml import (
    BaseDumper,
    BaseLoader,
    CollectionNode,
    Dumper,
    FullLoader,
    Loader,
    MappingNode,
    Node,
    SafeDumper,
    SafeLoader,
    ScalarNode,
    SequenceNode,
    load,
)

# Import from zero-dependency core module (avoids circular imports)
# from intellilog._internal.intelliyaml._core import pp
from intellipath import LogPath



def _get_resolve_object():
    """Lazy import to avoid circular dependencies."""
    # from intellilog._internal.intelliyaml.utils import resolve_object
    from intelliyaml.utils import resolve_object
    return resolve_object

type AnyLoader = BaseLoader | FullLoader | SafeLoader | Loader
type AnyDumper = BaseDumper | Dumper | SafeDumper
type AnyNode = Node | ScalarNode | CollectionNode | SequenceNode | MappingNode
_N = TypeVar("_N", bound=AnyNode)
_L = TypeVar("_L", bound=AnyLoader)
_R = TypeVar("_R", bound=Any)


class YAMLObjectMetaclass(type):
    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        kwds: dict[str, Any]
    ) -> type[BaseYmlObject]:
        cls = super().__new__(mcls, name, bases, kwds)

        if kwds.get("yaml_tag") is not None:
            if isinstance(cls.yaml_loader, list):
                for loader in cls.yaml_loader:
                    assert isinstance(loader, BaseLoader)
                    loader.add_constructor(cls.yaml_tag, cls.from_yaml)
            else:
                cls.yaml_loader.add_constructor(
                    cls.yaml_tag, cls.from_yaml
                )

            cls.yaml_dumper.add_representer(cls, cls.to_yaml)

        if kwds.get("yaml_multi_tag") is not None:
            if isinstance(cls.yaml_loader, list):
                for loader in cls.yaml_loader:
                    assert isinstance(loader, BaseLoader)
                    loader.add_multi_constructor(
                        f"tag:yaml.org,2002:{cls.yaml_multi_tag}:",
                        cls.from_yaml_multi,
                    )
            else:
                cls.yaml_loader.add_multi_constructor(
                    f"tag:yaml.org,2002:{cls.yaml_multi_tag}:",
                    cls.from_yaml_multi,
                )

            cls.yaml_dumper.add_representer(cls, cls.to_yaml)

        if kwds.get("regex_pattern") is not None:
            cls.yaml_loader.add_implicit_resolver(
                tag=cls.yaml_tag, regexp=cls.regex_pattern, first=None
            )
        
        return cls


class BaseYmlObject(Generic[_N, _L, _R], metaclass=YAMLObjectMetaclass):
    """Base class for YAML objects"""

    yaml_tag: ClassVar[str | None] = None
    yaml_multi_tag: ClassVar[str | None] = None
    yaml_flow_style: ClassVar[bool | None] = None
    yaml_loader: ClassVar[type[AnyLoader]] = FullLoader
    yaml_dumper: ClassVar[type[AnyDumper]] = Dumper

    regex_pattern: ClassVar[re.Pattern | None] = None

    default_config_file: ClassVar[Path] = LogPath.CONFIG

    def __init__(self, config_file: Path | None = None) -> None:
        super().__init__()

        self.config_file: Path = config_file or self.default_config_file
        self._stream: TextIOWrapper | None = None
        self.data: dict[str, Any] = {}

    @classmethod
    def from_yaml_multi(cls, loader: _L, suffix: str, node: _N) -> _R:
        """
        Construct object from YAML multi-constructor.

        :param cls: Class being constructed
        :param loader: YAML loader instance
        :type loader: _L
        :param suffix: Tag suffix for multi-constructors
        :type suffix: str
        :param node: YAML node to construct from
        :type node: _N
        :return: Constructed object
        :rtype: Any
        """
        raise NotImplementedError(
            f"{cls.__qualname__} defines yaml_multi_tag but does not implement from_yaml_multi"
        )

    @classmethod
    def from_yaml(cls, loader: _L, node: _N) -> _R:
        """Construct object from YAML.

        Args:
            cls: The class being constructed
            loader: The YAML loader instance
            node: The YAML node to construct from
        """
        raise NotImplementedError(
            f"{cls.__qualname__} must implement from_yaml method"
        )

    @classmethod
    def to_yaml(cls, dumper: Dumper, data: Any) -> MappingNode:  # ScalarNode:
        """Convert object to YAML node.

        Args:
            cls: The class being converted
            dumper: The YAML dumper instance
            data: The data to convert
        """
        if cls.yaml_tag is None:
            raise ValueError("yaml_tag must be defined to use to_yaml method")
        # return dumper.represent_scalar(tag=cls.yaml_tag, value=data)
        return dumper.represent_yaml_object(
            tag=cls.yaml_tag, data=data, cls=cls, flow_style=cls.yaml_flow_style
        )

    @property
    def stream(self) -> TextIOWrapper:
        if self._stream is None:
            self._stream = self.config_file.open("r")
        return self._stream

    def read_config(self) -> Self:
        self.data = load(stream=self.stream, Loader=self.yaml_loader)
        return self

    def __enter__(self) -> Self:
        return self.read_config()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            self._backup_config()
        finally:
            if self._stream is not None and self._stream.closed is False:
                self._stream.close()
                self._stream = None

    def load_yaml(self, data: str | None = None) -> dict[str, Any]:
        if data is None and not self.data:
            raise RuntimeError(
                "This method requires loaded data. Use 'with' statement or call read_config() first."
            )
        return self.yaml_loader(data or self.json_str()).get_data()

    def json_str(self, data: dict[str, Any] | None = None) -> str:
        if not self.data and data is None:
            raise RuntimeError(
                "This method requires loaded data. Use 'with' statement or call read_config() first."
            )
        return json.dumps(data or self.data, indent=4)

    def json_dict(self, data: str | None = None) -> dict[str, Any]:
        if not self.data and data is None:
            raise RuntimeError(
                "This method requires loaded data. Use 'with' statement or call read_config() first."
            )
        return json.loads(data or self.json_str())

    def replace(self, values: dict[str, str]) -> dict[str, Any]:
        """Expand env vars in a list of strings."""
        if not self.data:
            raise RuntimeError(
                "This method requires loaded data. Use 'with' statement or call read_config() first."
            )

        text = self.json_str()
        for key, value in values.items():
            text = text.replace(f"{{{key}}}", value)
        return self.json_dict(text)

    def _backup_config(self, backup_file: Path | None = None) -> None:
        """Backup the current configuration to a specified path."""

        original_content = self.stream.read()
        backup_path = backup_file or self.config_file.with_suffix(".backup.yaml")
        with backup_path.open("w") as backup:
            backup.write(original_content)
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__qualname__} config_file={getattr(self, 'config_file', None)!r}>"


class YmlEnvObject(BaseYmlObject[ScalarNode, FullLoader, str]):
    yaml_tag: ClassVar[str] = "!env"
    regex_pattern: ClassVar[re.Pattern] = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, config_file: Path | None = None) -> None:
        super().__init__(config_file=config_file)

    @classmethod
    def from_yaml(cls, loader: FullLoader, node: ScalarNode) -> str:
        value: str = loader.construct_scalar(node=node)
        return cls.expand_string(value)

    @classmethod
    def expand_string(cls, value: str) -> str:
        """Expand ${VAR} or ${VAR:-default} patterns in a string."""
        pattern = cls.regex_pattern

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

    @expand_env_vars.register(tuple)
    def _(self, data: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(self.expand_env_vars(item) for item in data)


class YmlPyObject(BaseYmlObject[MappingNode, FullLoader, str]):
    yaml_multi_tag: ClassVar[str] = "python/object"

    def __init__(
        self,
        config_file: Path | None = None,
    ) -> None:
        super().__init__(config_file=config_file)

    @classmethod
    def from_yaml_multi(cls, loader: FullLoader, suffix: str, node: MappingNode) -> str:
        ctx: dict[Hashable, str] = loader.construct_mapping(node=node, deep=True)
        if "." in suffix:
            module_name, object_name = suffix.rsplit(".", 1)
        else:
            module_name = "builtins"
            object_name = suffix
        if module_name not in sys.modules:
            try:
                __import__(module_name)
            except ImportError as e:
                raise ImportError(
                    f"Could not import module '{module_name}' for YAML object construction"
                ) from e
        module = sys.modules[module_name]
        if not hasattr(module, object_name):
            raise AttributeError(
                f"Module '{module_name}' has no attribute '{object_name}'"
            )
        obj = getattr(module, object_name)
        resolve_object = _get_resolve_object()  # Lazy import
        return resolve_object(ctx, obj)


# def main() -> None:
#     with YmlPyObject() as ymlp:
#         # pyLoaded = ymlp
#         parsed_config = ymlp.data

#     # pp(pyLoaded.__class__._logger_registry)
#     # pp(pyLoaded.__class__._yml_registry)
#     pp(parsed_config)
#     # pp(pyLoaded.load_yaml())


# if __name__ == "__main__":
#     main()
