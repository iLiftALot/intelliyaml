# ruff: noqa: UP047
from __future__ import annotations

import json
import re
import sys
from functools import singledispatchmethod
from importlib import import_module
from io import TextIOWrapper
from os import getenv
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, ClassVar, Hashable, Protocol, Self, Sequence, TypeVar

from pkg_registry import lazy_import
from yaml import (
    Dumper,
    FullLoader,
    Loader,
    MappingNode,
    Node,
    SafeDumper,
    SafeLoader,
    ScalarNode,
    UnsafeLoader,
    load,
)


intellipath = lazy_import("intellipath")
intellilog = lazy_import("intellilog")


YAML_TAG_PREFIX = "tag:yaml.org,2002:"


type AnyLoader = FullLoader | SafeLoader | Loader | UnsafeLoader
type LoaderClass = type[AnyLoader]
type LoaderSpecification = LoaderClass | Sequence[LoaderClass]
type DumperClass = type[Dumper | SafeDumper]


LoaderT_contra = TypeVar("LoaderT_contra", bound=AnyLoader, contravariant=True)
NodeT_contra = TypeVar("NodeT_contra", bound=Node, contravariant=True)
DumperT_contra = TypeVar("DumperT_contra", bound=Dumper | SafeDumper, contravariant=True)
DataT_contra = TypeVar("DataT_contra", contravariant=True)
ResultT_co = TypeVar("ResultT_co", covariant=True)


_SUPPORTED_LOADERS = (FullLoader, SafeLoader, Loader, UnsafeLoader)


class SingleConstructor(Protocol[LoaderT_contra, NodeT_contra, ResultT_co]):
    """Handler supporting one exact YAML tag."""

    @classmethod
    def from_yaml(cls, loader: LoaderT_contra, node: NodeT_contra) -> ResultT_co:
        """Construct a Python value from a YAML node."""
        ...


class MultiConstructor(Protocol[LoaderT_contra, NodeT_contra, ResultT_co]):
    """Handler supporting a YAML tag prefix."""

    @classmethod
    def from_yaml_multi(
        cls, loader: LoaderT_contra, suffix: str, node: NodeT_contra
    ) -> ResultT_co:
        """Construct a Python value from a YAML tag suffix and node."""
        ...


class Representer(Protocol[DumperT_contra, DataT_contra]):
    """Handler capable of representing a Python value as YAML."""

    @classmethod
    def to_yaml(cls, dumper: DumperT_contra, data: DataT_contra) -> Node:
        """Represent a Python value as a YAML node."""
        ...


def _get_resolve_object() -> Callable[[dict[Hashable, Any], Any], Any]:
    """Lazily import the object resolver to avoid circular imports."""
    from intelliyaml.utils import resolve_object

    return resolve_object


def _normalize_loaders(loaders: LoaderSpecification) -> tuple[LoaderClass, ...]:
    """Normalize one loader class or a sequence of loader classes."""
    normalized = (loaders,) if isinstance(loaders, type) else tuple(loaders)

    if not normalized:
        raise ValueError("At least one YAML loader must be configured")

    if not all(
        isinstance(loader, type) and issubclass(loader, _SUPPORTED_LOADERS)
        for loader in normalized
    ):
        raise TypeError("yaml_loader entries must be supported YAML loader classes")

    return normalized


def _normalize_prefix(tag: str) -> str:
    return f"{YAML_TAG_PREFIX}{tag}:"


def _require_string_metadata(handler: type, attribute: str) -> str:
    """Read and validate required string metadata from a handler."""
    value = getattr(handler, attribute, None)

    if not isinstance(value, str) or not value:
        raise ValueError(f"{handler.__qualname__}.{attribute} must be a non-empty string")

    return value


def _require_loaders(handler: type) -> tuple[LoaderClass, ...]:
    """Read and validate loader metadata from a handler."""
    loaders = getattr(handler, "yaml_loader", None)

    if loaders is None:
        raise ValueError(f"{handler.__qualname__}.yaml_loader must be configured")

    return _normalize_loaders(loaders)


def register_single_constructor(
    handler: type[SingleConstructor[LoaderT_contra, NodeT_contra, ResultT_co]],
) -> None:
    """Register a handler's exact-tag constructor."""
    yaml_tag = _require_string_metadata(handler, "yaml_tag")
    tag_prefix = _normalize_prefix(yaml_tag)

    for loader in _require_loaders(handler):
        loader.add_constructor(tag_prefix, handler.from_yaml)


def register_multi_constructor(
    handler: type[MultiConstructor[LoaderT_contra, NodeT_contra, ResultT_co]],
) -> None:
    """Register a handler's tag-prefix constructor."""
    yaml_multi_tag = _require_string_metadata(handler, "yaml_multi_tag")
    tag_prefix = _normalize_prefix(yaml_multi_tag)

    for loader in _require_loaders(handler):
        loader.add_multi_constructor(tag_prefix, handler.from_yaml_multi)


def register_implicit_resolver(
    handler: type[SingleConstructor[LoaderT_contra, NodeT_contra, ResultT_co]],
) -> None:
    """Register implicit resolution for a single-constructor handler.

    Requiring SingleConstructor here prevents registering an implicit tag
    without a callback capable of constructing that tag.
    """
    yaml_tag = _require_string_metadata(handler, "yaml_tag")
    tag_prefix = _normalize_prefix(yaml_tag)
    regex_pattern = getattr(handler, "regex_pattern", None)

    if not isinstance(regex_pattern, re.Pattern):
        raise TypeError(
            f"{handler.__qualname__}.regex_pattern must be a compiled pattern"
        )

    for loader in _require_loaders(handler):
        loader.add_implicit_resolver(tag=tag_prefix, regexp=regex_pattern, first=None)


def register_representer(
    represented_type: type[DataT_contra],
    handler: type[Representer[DumperT_contra, DataT_contra]],
    *,
    dumper: type[DumperT_contra],
) -> None:
    """Register a representer independently from constructors."""
    if not isinstance(dumper, type):
        raise TypeError("dumper must be a YAML dumper class")

    dumper.add_representer(represented_type, handler.to_yaml)


class YAMLBaseHandler:
    """Non-generic base for configuration-file lifecycle behavior.

    YAML callback methods are intentionally absent. Concrete handlers define
    only the constructor or representer capabilities they actually support.
    """

    yaml_tag: ClassVar[str | None] = None
    yaml_multi_tag: ClassVar[str | None] = None
    yaml_loader: ClassVar[LoaderSpecification] = [Loader, FullLoader, UnsafeLoader]
    yaml_dumper: ClassVar[DumperClass | None] = None
    yaml_flow_style: ClassVar[bool | None] = None
    regex_pattern: ClassVar[re.Pattern[str] | None] = None

    default_config_file: ClassVar[Path] = intellipath.LogPath.CONFIG

    def __init__(self, config_file: Path | None = None) -> None:
        self.config_file = config_file or self.default_config_file
        self._stream: TextIOWrapper | None = None
        self.data: dict[str, Any] = {}

        self.log = intellilog.initLog("intelliyaml", verbose=True, console_level="DEBUG")

    @property
    def stream(self) -> TextIOWrapper:
        if self._stream is None:
            self._stream = self.config_file.open("r")

        return self._stream

    def _lifecycle_loader(self) -> LoaderClass:
        """Return the single loader used by lifecycle operations."""
        loaders = _normalize_loaders(self.yaml_loader)

        if len(loaders) != 1:
            raise ValueError(
                f"{type(self).__qualname__}.yaml_loader must contain exactly "
                "one loader for read_config() and load_yaml()"
            )

        return loaders[0]

    def read_config(self) -> Self:
        loaded = load(stream=self.stream, Loader=self._lifecycle_loader())

        if loaded is None:
            self.data = {}
        elif isinstance(loaded, dict):
            self.data = loaded
        else:
            raise TypeError(
                f"The root YAML value must be a mapping, not {type(loaded).__qualname__}"
            )

        return self

    def __enter__(self) -> Self:
        return self.read_config()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._backup_config()
        finally:
            if self._stream is not None and not self._stream.closed:
                self._stream.close()
                self._stream = None

    def load_yaml(self, data: str | None = None) -> dict[str, Any]:
        if data is None:
            if not self.data:
                raise RuntimeError(
                    "This method requires loaded data. Use a 'with' statement "
                    "or call read_config() first."
                )

            data = self.json_str()

        loader = self._lifecycle_loader()(data)

        try:
            loaded = loader.get_single_data()
        finally:
            loader.dispose()

        if loaded is None:
            return {}

        if not isinstance(loaded, dict):
            raise TypeError(
                f"The root YAML value must be a mapping, not {type(loaded).__qualname__}"
            )

        return loaded

    def json_str(self, data: dict[str, Any] | None = None) -> str:
        selected_data = self.data if data is None else data

        if not selected_data:
            raise RuntimeError(
                "This method requires loaded data. Use a 'with' statement "
                "or call read_config() first."
            )

        return json.dumps(selected_data, indent=4)

    def json_dict(self, data: str | None = None) -> dict[str, Any]:
        if data is None:
            data = self.json_str()

        loaded: Any = json.loads(data)

        if not isinstance(loaded, dict):
            raise TypeError("The JSON root value must be an object")

        return loaded

    def replace(self, values: dict[str, str]) -> dict[str, Any]:
        if not self.data:
            raise RuntimeError(
                "This method requires loaded data. Use a 'with' statement "
                "or call read_config() first."
            )

        text = self.json_str()

        for key, value in values.items():
            text = text.replace(f"{{{key}}}", value)

        return self.json_dict(text)

    def _backup_config(self, backup_file: Path | None = None) -> None:
        """Back up the complete original configuration file."""
        backup_path = (
            backup_file
            if backup_file is not None
            else self.config_file.with_suffix(".backup.yaml")
        )

        # Reading from the path avoids relying on the stream's current offset.
        original_content = self.config_file.read_text()
        backup_path.write_text(original_content)

    def __repr__(self) -> str:
        return f"<{type(self).__qualname__} config_file={self.config_file!r}>"


class YamlEnvVariableExpander(YAMLBaseHandler):
    """Expand environment-variable expressions in scalar values."""

    yaml_tag = "env"
    yaml_loader = FullLoader
    regex_pattern = re.compile(r"\$\{([^}]+)\}")

    @classmethod
    def from_yaml(cls, loader: FullLoader, node: ScalarNode) -> str:
        value = loader.construct_scalar(node)
        return cls.expand_string(value)

    @classmethod
    def expand_string(cls, value: str) -> str:
        """Expand ${VAR} and ${VAR:-default} expressions."""

        def regex_replacer(match: re.Match[str]) -> str:
            expression = match.group(1)

            if ":-" in expression:
                variable_name, default = expression.split(":-", 1)
                return getenv(variable_name, default)

            return getenv(expression, match.group(0))

        pattern = cls.regex_pattern
        assert pattern is not None

        return pattern.sub(regex_replacer, value)

    @singledispatchmethod
    def expand_env_vars(self, data: Any) -> Any:
        """Recursively expand environment expressions."""
        return data

    @expand_env_vars.register
    def _(self, data: str) -> str:
        return self.expand_string(data)

    @expand_env_vars.register
    def _(self, data: dict) -> dict[str, Any]:
        return {key: self.expand_env_vars(value) for key, value in data.items()}

    @expand_env_vars.register
    def _(self, data: list) -> list[Any]:
        return [self.expand_env_vars(item) for item in data]

    @expand_env_vars.register
    def _(self, data: tuple) -> tuple[Any, ...]:
        return tuple(self.expand_env_vars(item) for item in data)


# These calls verify that YamlEnvVariableExpander structurally implements
# SingleConstructor[FullLoader, ScalarNode, str].
register_single_constructor(YamlEnvVariableExpander)
register_implicit_resolver(YamlEnvVariableExpander)


class YamlObjectLoader(YAMLBaseHandler):
    """Resolve tagged mappings into Python objects."""

    yaml_multi_tag = "python/object"
    yaml_loader = FullLoader

    @classmethod
    def from_yaml_multi(cls, loader: FullLoader, suffix: str, node: MappingNode) -> Any:
        context: dict[Hashable, Any] = loader.construct_mapping(node=node, deep=True)

        if "." in suffix:
            module_name, object_name = suffix.rsplit(".", 1)
        else:
            module_name, object_name = "builtins", suffix

        if module_name not in sys.modules:
            try:
                # __import__(module_name)
                import_module(module_name)
            except ImportError as error:
                raise ImportError(
                    f"Could not import module {module_name!r} "
                    "for YAML object construction"
                ) from error

        module = sys.modules[module_name]

        if not hasattr(module, object_name):
            raise AttributeError(
                f"Module {module_name!r} has no attribute {object_name!r}"
            )

        target = getattr(module, object_name)
        resolve_object = _get_resolve_object()

        return resolve_object(context, target)


# This independently verifies the multi-constructor capability.
register_multi_constructor(YamlObjectLoader)


def main() -> None:
    with YamlObjectLoader() as yaml_handler:
        parsed_config = yaml_handler.data

    logger = intellilog.initLog("intelliyaml.main")
    logger.debug(parsed_config)


if __name__ == "__main__":
    main()
