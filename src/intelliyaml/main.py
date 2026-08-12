from __future__ import annotations

import json
import re
import sys
# import importlib
from functools import singledispatchmethod
from io import TextIOWrapper
from os import getenv
from pathlib import Path
from typing import Any, ClassVar, Generic, Hashable, Self, TypeVar, cast

from pkg_registry import lazy_import
from yaml import (
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
    UnsafeLoader,
    load,
)


intellipath = lazy_import("intellipath")
intellilog = lazy_import("intellilog")


def _get_resolve_object():
    """Lazy import to avoid circular dependencies."""
    # from intellilog._internal.intelliyaml.utils import resolve_object
    from intelliyaml.utils import resolve_object

    return resolve_object


type AnyLoader = FullLoader | SafeLoader | Loader | UnsafeLoader
type AnyDumper = Dumper | SafeDumper
type AnyNode = Node | ScalarNode | CollectionNode | SequenceNode | MappingNode

_NodeType = TypeVar("_NodeType", bound=AnyNode)
_LoaderType = TypeVar("_LoaderType", bound=AnyLoader)
_DumperTypeOrNone = TypeVar("_DumperTypeOrNone", bound=AnyDumper | None)
_ReturnType = TypeVar("_ReturnType")
_TagTStrOrNone = TypeVar("_TagTStrOrNone", str, None)
_MultiTagTStrOrNone = TypeVar("_MultiTagTStrOrNone", str, None)
_MultiTagRegexTPatternOrNone = TypeVar(
    "_MultiTagRegexTPatternOrNone", re.Pattern[Any], None
)

YAMLObjectHandler = TypeVar(
    "YAMLObjectHandler",
    bound="YAMLObjectLike[AnyNode, AnyLoader, AnyDumper, Any, str, str, re.Pattern[Any]]",
)
YAML_TAG_PREFIX = "tag:yaml.org,2002:"


class YAMLObjectLike(
    Generic[
        _NodeType,
        _LoaderType,
        _DumperTypeOrNone,
        _ReturnType,
        _TagTStrOrNone,
        _MultiTagTStrOrNone,
        _MultiTagRegexTPatternOrNone,
    ]
):
    """A generic type representing a YAML object-like structure.

    :param _NodeType: The type of YAML node (e.g., ScalarNode, MappingNode).
    :type _NodeType: TypeVar["_NodeType", bound=Node | ScalarNode | CollectionNode | SequenceNode | MappingNode]
    :param _LoaderType: The type of YAML loader (e.g., FullLoader, SafeLoader).
    :type _LoaderType: TypeVar["_LoaderType", bound=BaseLoader | FullLoader | SafeLoader | Loader | UnsafeLoader]
    :param _DumperTypeOrNone: The type of YAML dumper (e.g., Dumper, SafeDumper) or None.
    :type _DumperTypeOrNone: TypeVar["_DumperTypeOrNone", AnyDumper, None]
    :param _ReturnType: The return type of the from_yaml and from_yaml_multi methods.
    :type _ReturnType: TypeVar["_ReturnType"]
    :param _TagTStrOrNone: The type of the YAML tag (str or None).
    :type _TagTStrOrNone: TypeVar["_TagTStrOrNone", str, None]
    :param _MultiTagTStrOrNone: The type of the YAML multi-tag (str or None).
    :type _MultiTagTStrOrNone: TypeVar["_MultiTagTStrOrNone", str, None]
    :param _MultiTagRegexTPatternOrNone: The type of the regex pattern for implicit resolvers (re.Pattern or None).
    :type _MultiTagRegexTPatternOrNone: TypeVar["_MultiTagRegexTPatternOrNone", re.Pattern[Any], None]
    """

    yaml_tag: _TagTStrOrNone
    yaml_multi_tag: _MultiTagTStrOrNone
    yaml_loader: type[_LoaderType] | list[type[_LoaderType]]
    yaml_dumper: type[_DumperTypeOrNone] | None
    yaml_flow_style: ClassVar[bool | None]
    regex_pattern: _MultiTagRegexTPatternOrNone

    @classmethod
    def from_yaml(cls, loader: _LoaderType, node: _NodeType) -> _ReturnType:
        """Construct an object from a YAML node."""
        raise NotImplementedError(f"{cls.__qualname__} must implement from_yaml method")

    @classmethod
    def from_yaml_multi(
        cls, loader: _LoaderType, suffix: str, node: _NodeType
    ) -> _ReturnType:
        """Construct an object from a YAML multi-constructor tag."""
        raise NotImplementedError(
            f"{cls.__qualname__} must implement from_yaml_multi method"
        )

    @classmethod
    def to_yaml(cls, dumper: _DumperTypeOrNone, data: Any) -> Node:
        """Convert an object to a YAML node."""
        raise NotImplementedError(f"{cls.__qualname__} must implement to_yaml method")


class YamlObjectHandlerRegistry:
    """Registry for YAML object handlers.

    This class maintains a registry of YAML object handlers, allowing for the registration
    and retrieval of handlers based on their associated YAML tags. It supports both single
    and multi-constructor YAML tags.
    """

    _registry: ClassVar[
        dict[
            str,
            type[
                YAMLObjectLike[
                    AnyNode,
                    AnyLoader,
                    Dumper | SafeDumper | None,
                    Any,
                    str,
                    str,
                    re.Pattern[Any],
                ]
            ],
        ]
    ] = {}

    @classmethod
    def register_handler(
        cls,
        handler_cls: type[
            YAMLObjectLike[
                AnyNode,
                AnyLoader,
                Dumper | SafeDumper | None,
                Any,
                str,
                str,
                re.Pattern[Any],
            ]
        ],
    ) -> None:
        """Register a YAML object handler.

        :param handler_cls: The handler class to register
        """
        yaml_tag = getattr(handler_cls, "yaml_tag", None)
        yaml_multi_tag = getattr(handler_cls, "yaml_multi_tag", None)

        if yaml_tag:
            cls._registry[yaml_tag] = handler_cls

        if yaml_multi_tag:
            cls._registry[f"{YAML_TAG_PREFIX}{yaml_multi_tag}:"] = handler_cls

    @classmethod
    def get_handler(
        cls, tag: str
    ) -> (
        type[
            YAMLObjectLike[
                AnyNode,
                AnyLoader,
                Dumper | SafeDumper | None,
                Any,
                str,
                str,
                re.Pattern[Any],
            ]
        ]
        | None
    ):
        """Retrieve a registered YAML object handler by tag.

        :param tag: The YAML tag associated with the handler
        :return: The registered handler class or None if not found
        """
        return cls._registry.get(tag)


class YAMLObjectMetaclass(type):
    """Metaclass for YAML object handlers.

    This metaclass automatically registers YAML constructors and representers based on
    the class attributes `yaml_tag`, `yaml_multi_tag`, and `regex_pattern`. It supports both single and multi-constructor YAML tags, as well as implicit resolvers for regex patterns.
    """

    __slots__ = ()

    def __new__(
        mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> type:
        yaml_cls = cast(
            type[
                YAMLObjectLike[
                    AnyNode, AnyLoader, AnyDumper | None, Any, str, str, re.Pattern[Any]
                ]
            ],
            super().__new__(mcls, name, bases, namespace, **kwargs),
        )
        yaml_loader: type[AnyLoader] | list[type[AnyLoader]] | None = (
            type.__getattribute__(yaml_cls, "yaml_loader")
        )
        yaml_dumper: type[AnyDumper] = type.__getattribute__(yaml_cls, "yaml_dumper")

        if (
            namespace.get("yaml_tag") is not None
            and namespace.get("yaml_loader") is not None
        ):
            yaml_tag: str = mcls.assert_yaml_tag(yaml_cls)
            assert yaml_loader is not None

            if isinstance(yaml_loader, list):
                for loader in yaml_loader:
                    loader.add_constructor(yaml_tag, yaml_cls.from_yaml)
            else:
                yaml_loader.add_constructor(yaml_tag, yaml_cls.from_yaml)

            if yaml_dumper is not None:
                yaml_dumper.add_representer(yaml_cls, yaml_cls.to_yaml)

        if (
            namespace.get("yaml_multi_tag") is not None
            and namespace.get("yaml_loader") is not None
        ):
            yaml_multi_tag: str = mcls.assert_multi_yaml_tag(yaml_cls)
            assert yaml_loader is not None

            if isinstance(yaml_loader, list):
                for loader in yaml_loader:
                    loader.add_multi_constructor(
                        f"{YAML_TAG_PREFIX}{yaml_multi_tag}:", yaml_cls.from_yaml_multi
                    )
            else:
                yaml_loader.add_multi_constructor(
                    f"{YAML_TAG_PREFIX}{yaml_multi_tag}:", yaml_cls.from_yaml_multi
                )

            yaml_dumper.add_representer(yaml_cls, yaml_cls.to_yaml)

        if (
            namespace.get("regex_pattern") is not None
            and namespace.get("yaml_tag") is not None
            and namespace.get("yaml_loader") is not None
        ):
            regex_pattern: re.Pattern[Any] = mcls.assert_regex_pattern(yaml_cls)
            yaml_tag: str = mcls.assert_yaml_tag(yaml_cls)
            assert yaml_loader is not None

            if isinstance(yaml_loader, list):
                for loader in yaml_loader:
                    assert isinstance(loader, BaseLoader)
                    loader.add_implicit_resolver(
                        tag=yaml_tag, regexp=regex_pattern, first=None
                    )
            else:
                yaml_loader.add_implicit_resolver(
                    tag=yaml_tag, regexp=regex_pattern, first=None
                )

        return yaml_cls

    @staticmethod
    def assert_yaml_tag(
        _cls: type[YAMLObjectLike[Any, Any, Any, Any, str, Any, Any]],
    ) -> str:
        yaml_tag: str = type.__getattribute__(_cls, "yaml_tag")
        return yaml_tag

    @staticmethod
    def assert_multi_yaml_tag(
        _cls: type[YAMLObjectLike[Any, Any, Any, Any, Any, str, Any]],
    ) -> str:
        yaml_multi_tag: str = type.__getattribute__(_cls, "yaml_multi_tag")
        return yaml_multi_tag

    @staticmethod
    def assert_regex_pattern(
        _cls: type[YAMLObjectLike[Any, Any, Any, Any, Any, Any, re.Pattern[Any]]],
    ) -> re.Pattern[Any]:
        regex_pattern: re.Pattern[Any] = type.__getattribute__(_cls, "regex_pattern")
        return regex_pattern


class YAMLBaseHandler(
    Generic[
        _NodeType,
        _LoaderType,
        _DumperTypeOrNone,
        _ReturnType,
        _TagTStrOrNone,
        _MultiTagTStrOrNone,
        _MultiTagRegexTPatternOrNone,
    ],
    metaclass=YAMLObjectMetaclass,
):
    """Base class for YAML objects.

    This class provides a framework for defining custom YAML objects with specific tags,
    loaders, and dumpers. It supports both single and multi-constructor YAML tags, as
    well as implicit resolvers for regex patterns.

    :param _NodeType: The type of YAML node (e.g., ScalarNode, MappingNode).
    :type _NodeType: TypeVar["_NodeType", bound=Node | ScalarNode | CollectionNode | SequenceNode | MappingNode]
    :param _LoaderType: The type of YAML loader (e.g., FullLoader, SafeLoader).
    :type _LoaderType: TypeVar["_LoaderType", bound=BaseLoader | FullLoader | SafeLoader | Loader | UnsafeLoader]
    :param _DumperTypeOrNone: The type of YAML dumper (e.g., Dumper, SafeDumper) or None.
    :type _DumperTypeOrNone: TypeVar["_DumperTypeOrNone", AnyDumper, None]
    :param _ReturnType: The return type of the from_yaml and from_yaml_multi methods.
    :type _ReturnType: TypeVar["_ReturnType"]
    :param _TagTStrOrNone: The type of the YAML tag (str or None).
    :type _TagTStrOrNone: TypeVar["_TagTStrOrNone", str, None]
    :param _MultiTagTStrOrNone: The type of the YAML multi-tag (str or None).
    :type _MultiTagTStrOrNone: TypeVar["_MultiTagTStrOrNone", str, None]
    :param _MultiTagRegexTPatternOrNone: The type of the regex pattern for implicit resolvers (re.Pattern or None).
    :type _MultiTagRegexTPatternOrNone: TypeVar["_MultiTagRegexTPatternOrNone", re.Pattern[Any], None]
    """

    yaml_tag: _TagTStrOrNone
    yaml_multi_tag: _MultiTagTStrOrNone
    yaml_loader: type[_LoaderType] = cast(type[_LoaderType], Loader)
    yaml_dumper: type[_DumperTypeOrNone] | None = cast(type[_DumperTypeOrNone], Dumper)
    yaml_flow_style: ClassVar[bool | None] = None
    regex_pattern: _MultiTagRegexTPatternOrNone

    default_config_file: ClassVar[Path] = intellipath.LogPath.CONFIG

    def __init__(self, config_file: Path | None = None) -> None:
        super().__init__()

        self.config_file: Path = config_file or self.default_config_file
        self._stream: TextIOWrapper | None = None
        self.data: dict[str, Any] = {}

        self.log = intellilog.initLog("intelliyaml", verbose=True, console_level=None)
        self.log.debug({k: getattr(self, k) for k in dir(self)})

    @classmethod
    def from_yaml_multi(
        cls, loader: _LoaderType, suffix: str, node: _NodeType
    ) -> _ReturnType:
        """
        Construct object from YAML multi-constructor.

        :param cls: Class being constructed
        :param loader: YAML loader instance
        :type loader: _LoaderType
        :param suffix: Tag suffix for multi-constructors
        :type suffix: str
        :param node: YAML node to construct from
        :type node: _NodeType
        :return: Constructed object
        :rtype: Any
        """
        raise NotImplementedError(
            f"{cls.__qualname__} defines yaml_multi_tag but does not implement from_yaml_multi"
        )

    @classmethod
    def from_yaml(cls, loader: _LoaderType, node: _NodeType) -> _ReturnType:
        """Construct object from YAML.

        Args:
            cls: The class being constructed
            loader: The YAML loader instance
            node: The YAML node to construct from
        """
        raise NotImplementedError(f"{cls.__qualname__} must implement from_yaml method")

    @classmethod
    def to_yaml(cls, dumper: _DumperTypeOrNone, data: Any) -> MappingNode:  # ScalarNode:
        """Convert object to YAML node.

        Args:
            cls: The class being converted
            dumper: The YAML dumper instance
            data: The data to convert
        """
        if cls.yaml_tag is None:
            raise ValueError("yaml_tag must be defined to use to_yaml method")
        if dumper is None:
            raise ValueError("dumper must be provided to use to_yaml method")
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
        if data is None:
            if not self.data:
                raise RuntimeError(
                    "This method requires loaded data. Use 'with' statement or call read_config() first."
                )

            data = self.json_str()

        loader_inst = self.yaml_loader(data)
        return loader_inst.get_data()

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


class YamlEnvVariableExpander(
    YAMLBaseHandler[ScalarNode, FullLoader, Dumper, str, str, None, re.Pattern[str]]
):
    yaml_tag: str = f"{YAML_TAG_PREFIX}env/expand"
    yaml_loader: type[FullLoader] = FullLoader
    yaml_dumper = Dumper
    regex_pattern = re.compile(r"\$\{([^}]+)\}")

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


class YamlObjectLoader(
    YAMLBaseHandler[MappingNode, FullLoader, Any, str, None, str, None]
):
    yaml_multi_tag = "python/object"
    yaml_loader = FullLoader

    def __init__(self, config_file: Path | None = None) -> None:
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
                # importlib.import_module(module_name)
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


def main() -> None:
    with YamlObjectLoader() as ymlp:
        parsed_config = ymlp.data

    with YamlEnvVariableExpander() as ymlp:
        expanded_config = ymlp.expand_env_vars(parsed_config)

    logger = intellilog.initLog("intelliyaml.main")
    # logger.debug(parsed_config)
    logger.debug(expanded_config)


if __name__ == "__main__":
    main()
