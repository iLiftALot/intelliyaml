import yaml
from dataclasses import dataclass, asdict
from typing import Callable, overload, dataclass_transform


@dataclass_transform()
@overload
def yamldataclass[T](
    cls: type[T],
    *,
    yaml_tag: str | None = None,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
) -> type[T]:
    """@yamldataclass (no parens) → receives the class directly, returns type[T]"""
    ...


@dataclass_transform()
@overload
def yamldataclass[T](
    cls: None = None,
    *,
    yaml_tag: str | None = None,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
) -> Callable[[type[T]], type[T]]:
    """@yamldataclass() (with parens) → returns a callable that takes and returns type[T]"""
    ...

# ?  @dataclass(match_args=True, kw_only=True, repr=True)
# > ((type[_T@dataclass]) -> type[_T@dataclass])
# ?  @yamldataclass(match_args=True, kw_only=True, repr=True)
# > ((type[T@yamldataclass]) -> type[T@yamldataclass])

@dataclass_transform()
def yamldataclass[T](
    cls: type[T] | None = None,
    *,
    yaml_tag: str | None = None,
    init: bool = True,
    repr: bool = True,
    eq: bool = True,
    order: bool = False,
    unsafe_hash: bool = False,
    frozen: bool = False,
    match_args: bool = True,
    kw_only: bool = False,
    slots: bool = False,
    weakref_slot: bool = False,
) -> type[T] | Callable[[type[T]], type[T]]:
    """Decorator to create a YAML-serializable dataclass."""

    def wrap(cls):
        # Apply dataclass decorator first with all options
        dataclass_decorator = dataclass(
            init=init,
            repr=repr,
            eq=eq,
            order=order,
            unsafe_hash=unsafe_hash,
            frozen=frozen,
            match_args=match_args,
            kw_only=kw_only,
            slots=slots,
            weakref_slot=weakref_slot,
        )
        cls = dataclass_decorator(cls)

        # Set yaml_tag (use class attribute or generate from class name)
        tag = yaml_tag or getattr(cls, "yaml_tag", f"!{cls.__name__}")
        cls.yaml_tag = tag

        @classmethod
        def from_yaml(klass, loader, node):
            values = loader.construct_mapping(node, deep=True)
            return klass(**values)

        @classmethod
        def to_yaml(klass, dumper, data):
            return dumper.represent_mapping(klass.yaml_tag, asdict(data))

        cls.from_yaml = from_yaml
        cls.to_yaml = to_yaml

        # Register with YAML
        yaml.FullLoader.add_constructor(cls.yaml_tag, cls.from_yaml)
        yaml.Dumper.add_representer(cls, cls.to_yaml)

        return cls

    # Handle both @yamldataclass and @yamldataclass() syntax
    if cls is None:
        return wrap
    return wrap(cls)
