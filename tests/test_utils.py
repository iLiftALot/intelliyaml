"""Focused regression tests for the expression and operation resolvers."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Hashable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest  # pyright: ignore[reportMissingImports]


def _load_utils_module() -> Any:
    """Load utils.py without executing intelliyaml's package-level side effects."""
    module_name = "_intelliyaml_utils_under_test"
    module_path = Path(__file__).parents[1] / "src" / "intelliyaml" / "utils.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


utils = _load_utils_module()


class ResolverTarget:
    ROOT = Path("/tmp/intelliyaml")
    numbers: ClassVar[list[int]] = [2, 3, 4]
    settings: ClassVar[dict[str, str]] = {"host": "localhost"}

    @staticmethod
    def combine(prefix: str, value: int, *, suffix: str) -> str:
        return f"{prefix}{value}{suffix}"


@pytest.mark.parametrize("key", ["get", "attr"])
def test_resolve_object_supports_attribute_operation_names(key: str) -> None:
    assert utils.resolve_object({key: "ROOT"}, ResolverTarget) == ResolverTarget.ROOT


def test_resolve_object_executes_calls_and_chains() -> None:
    context = {
        "chain": [
            {"call": "combine", "args": ["value=", 3], "kwargs": {"suffix": "!"}},
            {"op": "+", "right": " done"},
        ]
    }

    assert utils.resolve_object(context, ResolverTarget) == "value=3! done"


def test_resolve_object_calls_the_target_itself() -> None:
    assert utils.resolve_object({"call": None, "args": ["17"]}, int) == 17


def test_resolve_object_requires_a_callable_target() -> None:
    with pytest.raises(TypeError, match="is not callable"):
        utils.resolve_object({"call": None}, object())


def test_resolve_object_indexes_mappings_and_sequences() -> None:
    mapping_context = {"chain": [{"get": "settings"}, {"index": "host"}]}
    sequence_index_context = {"chain": [{"get": "numbers"}, {"index": 1}]}
    sequence_value_context = {"index": "last"}

    assert utils.resolve_object(mapping_context, ResolverTarget) == "localhost"
    assert utils.resolve_object(sequence_index_context, ResolverTarget) == 3
    assert utils.resolve_object(sequence_value_context, ["first", "last"]) == "last"


def test_resolve_object_supports_nested_chains() -> None:
    context = {
        "chain": [
            {"value": 2},
            {"chain": [{"op": "**", "value": 3}, {"op": "+", "value": 1}]},
        ]
    }

    assert utils.resolve_object(context, ResolverTarget) == 9


def test_chain_accepts_documented_debug_alias(capsys: pytest.CaptureFixture[str]) -> None:
    result = utils.resolve_object(
        {"_debug": True, "chain": [{"get": "ROOT"}]}, ResolverTarget
    )

    assert result == ResolverTarget.ROOT
    assert "Chain step" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("numbers[0] + numbers[1] * numbers[2]", 14),
        ("numbers[2] // numbers[0]", 2),
        ("numbers[2] % numbers[1]", 1),
        ("numbers[0] ** numbers[1] ** numbers[0]", 512),
        ('ROOT / "logs" / "app.log"', ResolverTarget.ROOT / "logs" / "app.log"),
        ('combine("n=", numbers[1], "!")', "n=3!"),
    ],
)
def test_expression_parser_evaluates_supported_expressions(
    expression: str, expected: object
) -> None:
    target = SimpleNamespace(
        ROOT=ResolverTarget.ROOT,
        numbers=ResolverTarget.numbers,
        combine=lambda prefix, value, suffix: f"{prefix}{value}{suffix}",
    )

    assert utils.ExpressionParser(expression).evaluate(target) == expected


def test_expression_parser_decodes_escaped_strings() -> None:
    target = SimpleNamespace(echo=lambda value: value)

    assert utils.ExpressionParser(r'echo("quoted: \"yes\"")').evaluate(target) == (
        'quoted: "yes"'
    )


@pytest.mark.parametrize(
    "expression",
    ["numbers $ numbers", "numbers numbers", "numbers[0", "numbers[0]]", '"unterminated'],
)
def test_expression_parser_rejects_invalid_or_unconsumed_input(expression: str) -> None:
    with pytest.raises(SyntaxError):
        utils.ExpressionParser(expression).evaluate(ResolverTarget)


def test_operation_kind_must_match_operation_model() -> None:
    with pytest.raises(TypeError, match="requires GetOperation"):
        utils.Operation(
            kind="get", operation=utils.ValueOperation(value="not an attribute")
        )


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"get": "ROOT", "expr": "ROOT"},
        {"get": "ROOT", "unknown": True},
        {"op": "+"},
        {"chain": "get"},
        {"chain": [{"get": "ROOT"}, 1]},
        {1: "ROOT"},
    ],
)
def test_operation_builder_rejects_ambiguous_or_incomplete_contexts(
    context: dict[Hashable, object],
) -> None:
    with pytest.raises(ValueError):
        utils.operation_builder(context)
