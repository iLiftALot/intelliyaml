from __future__ import annotations

import json
import re
from abc import ABC, ABCMeta, abstractmethod
from functools import partial, singledispatchmethod
from logging import Logger
from os import getenv
from typing import Any, ClassVar, Self

from dotenv import load_dotenv
from intellipath import Path
from rich.console import Console
from rich.pretty import pprint
from yaml import (
    BaseDumper,
    BaseLoader,
    Dumper,
    FullLoader,
    MappingNode,
    ScalarNode,
    YAMLObject,
    YAMLObjectMetaclass,
    load,
)


load_dotenv()  # Load environment variables from a .env file if present
console = Console()
pp = partial(pprint, console=console, expand_all=True)


class YAMLObjectABCMeta(YAMLObjectMetaclass, ABCMeta):
    """Combined metaclass for YAMLObject + ABC support."""

    _yml_registry: ClassVar[dict[str, BaseYmlLoader]] = {}
    _logger_registry: ClassVar[dict[str, Logger]] = {}

    def __init__(cls: BaseYmlLoader, name, bases, kwds) -> None:
        super().__init__(name, bases, kwds)
        print(f"Initialized {cls.__qualname__} with YAMLObjectABCMeta")

        if "yaml_multi_tag" in kwds and kwds["yaml_multi_tag"] is not None:
            if isinstance(cls.yaml_loader, list):
                for loader in cls.yaml_loader:
                    assert isinstance(loader, BaseLoader)
                    loader.add_multi_constructor(
                        f"tag:yaml.org,2002:{cls.yaml_multi_tag}:", cls.from_yaml
                    )
            else:
                cls.yaml_loader.add_multi_constructor(
                    f"tag:yaml.org,2002:{cls.yaml_multi_tag}:", cls.from_yaml
                )

            cls.yaml_dumper.add_representer(cls, cls.to_yaml)

    def __call__(cls, *args, **kwargs):
        from_init_subclass = kwargs.get("from_init_subclass", False)

        # During class definition, create minimal instance (no __init__)
        if from_init_subclass:
            instance = cls.__new__(cls)
            # Set minimal attributes directly, NO logger calls
            instance.config_file = cls.default_config_file
            instance.data = {}
            instance.env_loader = None  # Will be set later
            instance.py_parser = None  # Will be set later
            return instance

        # Normal instantiation - check cache first
        cached = cls._yml_registry.get(cls.__qualname__)
        if cached is not None:
            # Optionally update with new config_file if provided
            if args or kwargs.get("config_file"):
                cached.config_file = kwargs.get("config_file") or args[0]
            # Wire up dependencies if not already set (shell instances have None)
            if cached.env_loader is None:
                cached.env_loader = cls._yml_registry.get("YmlEnvLoader")
            if cached.py_parser is None:
                cached.py_parser = cls._yml_registry.get("YmlPyLoader")
            return cached

        # Full instantiation - NOW safe to call __init__
        # At this point, all subclasses are registered, so deps are available
        instance = super().__call__(*args, **kwargs)

        # Post-init: wire up dependencies from registry
        instance.env_loader = cls._yml_registry.get("YmlEnvLoader")
        instance.py_parser = cls._yml_registry.get("YmlPyLoader")

        cls._yml_registry[cls.__qualname__] = instance

        return instance


class BaseYmlLoader(YAMLObject, ABC, metaclass=YAMLObjectABCMeta):
    """YAML loader that expands environment variables in the form ${VAR} or ${VAR:-default}"""

    yaml_tag: ClassVar[str | None] = None
    yaml_multi_tag: ClassVar[str | None] = None
    yaml_flow_style: ClassVar[bool | None] = None
    yaml_loader: ClassVar[type[BaseLoader]] = FullLoader
    yaml_dumper: ClassVar[type[BaseDumper]] = Dumper

    default_config_file: ClassVar[Path] = Path(
        # "/Users/nicholascorbin/CodeProjects/intelliyaml/src/intelliyaml/test_logging_config.yaml"
        "/Users/nicholascorbin/CodeProjects/intelliyaml/src/intelliyaml/test_env.yaml"
    )

    def __init__(self, config_file: Path | None = None, **kwargs) -> None:
        super().__init__()

        self.config_file = config_file or self.default_config_file

        for key, value in kwargs.items():
            setattr(self, key, value)

        self.data: dict[str, Any] = {}

        # env_loader and py_parser are set by __call__ post-init

    def __init_subclass__(cls) -> None:
        if cls.__qualname__ in cls._yml_registry:
            return  # Already registered

        instance = cls(from_init_subclass=True)
        cls._yml_registry[cls.__qualname__] = instance

    @classmethod
    @abstractmethod
    def from_yaml(cls, loader, node):
        raise NotImplementedError()

    @classmethod
    @abstractmethod
    def to_yaml(cls, dumper, data):
        raise NotImplementedError()

    def read_config(self) -> None:
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
        self.backup_config()

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

    def backup_config(self, backup_file: Path | None = None) -> None:
        """Backup the current configuration to a specified path."""

        with open(self.config_file, "r") as original:
            original_content = original.read()

        backup_path = backup_file or self.config_file.with_suffix(".backup.yaml")
        with backup_path.open("w") as backup:
            backup.write(original_content)


class YmlEnvLoader(BaseYmlLoader):
    yaml_tag: ClassVar[str] = "!env"
    env_var_pattern: ClassVar[re.Pattern] = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, config_file: Path | None = None, **kwargs) -> None:
        super().__init__(config_file=config_file, **kwargs)

        # Register the implicit resolver for environment variable patterns
        self.yaml_loader.add_implicit_resolver(
            tag=self.yaml_tag, regexp=self.env_var_pattern, first=None
        )

    @classmethod
    def from_yaml(cls, loader: FullLoader, node: ScalarNode) -> str:
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

    yaml_multi_tag: ClassVar[str] = "python/object/attr"
    yaml_loader: ClassVar[type[FullLoader]] = FullLoader

    def __init__(self, config_file: Path | None = None, **kwargs) -> None:
        super().__init__(config_file=config_file, **kwargs)

    @classmethod
    def from_yaml(cls, loader: FullLoader, suffix: str, node: MappingNode) -> str:
        ctx: dict[str, str] = loader.construct_mapping(node=node, deep=True)
        obj: object = loader.find_python_name(suffix, node.start_mark)
        attr: str = ctx["attr"]
        file_name: str = ctx.get("file_name", "app.log")
        value: Path = getattr(obj, attr) / file_name
        return value.to_str()

    @classmethod
    def to_yaml(cls, dumper: Dumper, data: str) -> ScalarNode:
        return dumper.represent_scalar(tag=cls.yaml_tag, value=data)


def main() -> None:
    with YmlEnvLoader() as yml:
        y = yml
        env_config = yml.data

    pp(env_config)

    with YmlPyLoader(
        Path(
            "/Users/nicholascorbin/CodeProjects/intelliyaml/src/intelliyaml/test_logging_config.yaml"
        )
    ) as ymlp:
        pyLoaded = ymlp
        parsed_config = ymlp.data

    pp(pyLoaded.__class__._logger_registry)
    pp(pyLoaded.__class__._yml_registry)
    pp(parsed_config)

    pp(pyLoaded.load_yaml())


if __name__ == "__main__":
    main()
