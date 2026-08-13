from __future__ import annotations

from intellifunctools import functools
import operator
import re

# from dataclasses import dataclass, field
from pydantic import BaseModel, Field, model_validator
from typing import Any, ClassVar, Literal, Self, cast, get_args
from collections.abc import Callable, Mapping, Sequence


# ============================================================================
# Expression-Based Object Resolver
# ============================================================================


type OperationKind = Literal["get", "call", "op", "index", "value", "chain", "expr"]
OpValue = Literal["/", "+", "-", "*", "//", "%", "**", "@", "|", "&"]


class OperationBase(BaseModel):
    debug: bool = Field(default=False)


class ValueOperation(OperationBase):
    """Literal value operation."""

    value: Any


class GetOperation(OperationBase):
    """Get attribute operation."""

    get: str


class CallOperation(OperationBase):
    """Call method operation."""

    call: str | None = None  # None means call the object itself
    args: tuple[Any, ...] = Field(default_factory=tuple)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class OpOperation(OperationBase):
    """Binary operator operation."""

    op: OpValue
    value: Any | None = None


class IndexOperation(OperationBase):
    """Indexing operation."""

    index: str | int


class ExpressionOperation(OperationBase):
    """Expression operation."""

    expr: str


class ChainOperation(OperationBase):
    """Chain of operations."""

    chain: list[OperationType]


type OperationType = (
    ValueOperation
    | GetOperation
    | CallOperation
    | OpOperation
    | IndexOperation
    | ExpressionOperation
    | ChainOperation
)


class Operation(BaseModel):
    """Represents an operation context."""

    kind: OperationKind
    operation: OperationType

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        kind = self.kind
        op = self.operation

        if kind == "chain" and not isinstance(op, ChainOperation):
            raise ValueError(
                f"Operation must be a list of SingleOperationType for kind 'chain'\n...got {type(op)} instead\n...with value:\n{op}"
            )

        if kind != "chain" and isinstance(op, ChainOperation):
            raise ValueError(
                f"Operation cannot be a list of SingleOperationType for non-'chain' kinds\n...got {type(op)} instead\n...with value:\n{op}"
            )

        return self


class ExpressionResolver:
    """
    A powerful expression-based resolver for dynamic Python object resolution in YAML files.

    Supports:
        - Attribute access: {"get": "attr_name"}
        - Method calls: {"call": "method_name", "args": [...], "kwargs": {...}}
        - Chained operations: {"chain": [{"get": "attr"}, {"call": "method"}]}
        - Binary operators: {"op": "/", "right": "value"} (for path joining, etc.)
        - Indexing: {"index": "key"} or {"index": 0}
        - Direct value: {"value": "literal_value"}

    .. Example::
        .. code:: yaml
        filename: !!python/object:intellipath.LogPath
          chain:
            - get: LOGS
            - op: "/"
            - value: "app.log"
    """

    # Supported binary operators
    OPERATORS: ClassVar[dict[OpValue, Callable[[Any, Any], Any]]] = {
        "/": operator.truediv,
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
        "//": operator.floordiv,
        "%": operator.mod,
        "**": operator.pow,
        "@": operator.matmul,
        "|": operator.or_,
        "&": operator.and_,
    }

    def __init__(self, obj: object) -> None:
        self.obj = obj

    @functools.singledispatchmethod
    def _resolve(self, operation) -> Any:
        """
        Resolve the object using the context configuration.

        Dispatch based on context keys:
            - "chain": Execute a chain of operations
            - "get"/"attr": Get an attribute
            - "call": Call a method or the object itself
            - "op": Apply a binary operator
            - "index": Index into the object
            - "value": Return a literal value
            - "expr": Parse and evaluate a string expression
        """
        raise NotImplementedError(f"Unsupported operation type: {type(operation)}")

    @_resolve.register(ChainOperation)
    def _chain(self, operation: ChainOperation) -> Any:
        """Execute a chain of operations sequentially."""
        for step in operation.chain:
            self.obj = self._resolve(step)
            if operation.debug:
                print(f"  Chain step {step} -> {self.obj}")
        return self.obj

    @_resolve.register(ExpressionOperation)
    def _expression(self, operation: ExpressionOperation) -> Any:
        """
        Parse and resolve a simple dot-notation expression.

        Supports expressions like:
            - "LOGS"           -> getattr(obj, "LOGS")
            - "LOGS / app.log" -> getattr(obj, "LOGS") / "app.log"
            - "method()"       -> obj.method()
            - "attr.method(x)" -> obj.attr.method("x")
        """
        return ExpressionParser(operation.expr, debug=operation.debug).evaluate(self.obj)

    @_resolve.register_all(
        ValueOperation, GetOperation, CallOperation, OpOperation, IndexOperation
    )
    def _resolve_single(self, operation) -> Any:
        """Resolve a single operation from context."""

        # Attribute access
        if isinstance(operation, GetOperation):
            attr_name = operation.get
            result = getattr(self.obj, attr_name)

            if operation.debug:
                print(f"  getattr({self.obj}, {attr_name!r}) -> {result}")

            return result

        # Method/callable invocation
        if isinstance(operation, CallOperation):
            method_name = operation.call
            args = operation.args if hasattr(operation, "args") else ()
            kwargs = operation.kwargs if hasattr(operation, "kwargs") else {}

            if method_name is None:
                assert callable(self.obj), f"Object {self.obj} is not callable"
                # Call the object itself
                result = self.obj(*args, **kwargs)
            else:
                # Call a method on the object
                method = getattr(self.obj, method_name)
                result = method(*args, **kwargs)

            if operation.debug:
                print(f"  {self.obj}.{method_name}(*{args}, **{kwargs}) -> {result}")

            return result

        # Binary operator
        if isinstance(operation, OpOperation):
            op_name = operation.op
            value = operation.value
            op_func = self.OPERATORS.get(op_name)

            if op_func is None:
                raise ValueError(f"Unsupported operator: {op_name}")

            result = op_func(self.obj, value)

            if operation.debug:
                print(f"  {self.obj} {op_name} {value} -> {result}")

            return result

        # Indexing
        if isinstance(operation, IndexOperation):
            key = operation.index

            try:
                if isinstance(self.obj, Mapping):
                    result = self.obj[key]
                elif isinstance(self.obj, Sequence):
                    if not isinstance(key, int):
                        key = self.obj.index(key, 0, -1)
                        result = self.obj[key]
                    else:
                        result = self.obj[key]
                else:
                    raise TypeError(f"Object {self.obj!r} is not indexable with key {key!r}")
            except (KeyError, IndexError, ValueError, TypeError) as e:
                raise ValueError(f"Failed to index {self.obj!r} with key {key!r}: {e}") from e

            if operation.debug:
                print(f"  {self.obj}[{key!r}] -> {result}")

            return result

        # Literal value (passthrough)
        if isinstance(operation, ValueOperation):
            if operation.debug:
                print(f"  Returning literal value: {operation.value!r}")

            return operation.value

        raise ValueError(f"Unknown operation: {operation}")


class ExpressionParser:
    """
    Parse and evaluate simple Python-like expressions.

    Grammar (simplified):
        expr     := term (('+' | '-' | '/' | '*') term)*
        term     := primary ('.' IDENT | '(' args ')' | '[' key ']')*
        primary  := IDENT | STRING | NUMBER
    """

    # Token patterns
    TOKEN_PATTERN = re.compile(
        r"""
        (?P<STRING>"[^"]*"|'[^']*')         |  # String literals
        (?P<NUMBER>\d+(?:\.\d+)?)           |  # Numbers
        (?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*)   |  # Identifiers
        (?P<OP>[+\-*/|&@])                  |  # Operators
        (?P<DOT>\.)                         |  # Dot accessor
        (?P<LPAREN>\()                      |  # Open paren
        (?P<RPAREN>\))                      |  # Close paren
        (?P<LBRACKET>\[)                    |  # Open bracket
        (?P<RBRACKET>\])                    |  # Close bracket
        (?P<COMMA>,)                        |  # Comma
        (?P<WS>\s+)                            # Whitespace (ignored)
    """,
        re.VERBOSE,
    )

    def __init__(self, expr: str, debug: bool = False) -> None:
        self.expr = expr
        self.debug = debug
        self.tokens = self._tokenize(expr)
        self.pos = 0

    def _tokenize(self, expr: str) -> list[tuple[str, str]]:
        """Tokenize the expression."""
        tokens = []
        for match in self.TOKEN_PATTERN.finditer(expr):
            for name, value in match.groupdict().items():
                if value is not None and name != "WS":
                    tokens.append((name, value))
                    break
        return tokens

    def _peek(self) -> tuple[str, str] | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def _advance(self) -> tuple[str, str]:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _expect(self, kind: str) -> str:
        token = self._peek()
        if token is None or token[0] != kind:
            raise SyntaxError(f"Expected {kind}, got {token}")
        return self._advance()[1]

    def evaluate(self, obj: object) -> Any:
        """Evaluate the expression with the given object as context."""
        if self.debug:
            print(f"Evaluating expression: {self.expr}")
        return self._parse_expr(obj)

    def _parse_expr(self, obj: object) -> Any:
        """Parse additive/multiplicative expressions."""
        left = self._parse_term(obj)
        token = self._peek()
        while token and token[0] == "OP":
            op = self._advance()[1]
            assert op in get_args(OpValue), f"Unsupported operator: {op}"
            right = self._parse_term(obj)
            op_func = ExpressionResolver.OPERATORS.get(cast(OpValue, op))
            if op_func:
                left = op_func(left, right)
            else:
                raise ValueError(f"Unknown operator: {op}")
            token = self._peek()

        return left

    def _parse_term(self, obj: object) -> Any:
        """Parse a term with accessor chains."""
        result = self._parse_primary(obj)

        while self._peek():
            token = self._peek()

            if not token:
                break

            if token[0] == "DOT":
                self._advance()
                ident = self._expect("IDENT")
                result = getattr(result, ident)

            elif token[0] == "LPAREN":
                self._advance()
                args = self._parse_args(obj)
                self._expect("RPAREN")
                result = result(*args)

            elif token[0] == "LBRACKET":
                self._advance()
                key = self._parse_primary(obj)
                self._expect("RBRACKET")
                result = result[key]

            else:
                break

        return result

    def _parse_primary(self, obj: object) -> Any:
        """Parse a primary value (identifier, string, or number)."""
        token = self._peek()
        if token is None:
            raise SyntaxError(f"Unexpected end of expression: {self.expr}")

        if token[0] == "IDENT":
            name = self._advance()[1]
            # First identifier resolves against the object
            return getattr(obj, name)

        elif token[0] == "STRING":
            value = self._advance()[1]
            return value[1:-1]  # Strip quotes

        elif token[0] == "NUMBER":
            value = self._advance()[1]
            return float(value) if "." in value else int(value)

        raise SyntaxError(f"Unexpected token: {token}")

    def _parse_args(self, obj: object) -> list[Any]:
        """Parse function arguments."""
        args = []
        token = self._peek()
        while token and token[0] != "RPAREN":
            if args:
                self._expect("COMMA")
            args.append(self._parse_expr(obj))
            token = self._peek()
        return args


def operation_builder(ctx: dict) -> Operation:
    """Build an Operation object from a context dictionary."""

    op_type_map: dict[OperationKind, type[OperationType]] = {
        "get": GetOperation,
        "call": CallOperation,
        "op": OpOperation,
        "index": IndexOperation,
        "expr": ExpressionOperation,
        "value": ValueOperation,
    }

    if "chain" in ctx:
        chain_ops: list[OperationType] = [
            operation_builder(op_ctx).operation for op_ctx in ctx["chain"]
        ]
        return Operation(kind="chain", operation=ChainOperation(chain=chain_ops))

    for key, cls in op_type_map.items():
        if key in ctx:
            return Operation(kind=key, operation=cls(**ctx))

    raise ValueError(f"Unknown operation context: {ctx}")


def resolve_object(ctx: dict, obj: object) -> Any:
    """Resolve an object based on the provided operation context."""

    op_ctx = operation_builder(ctx)
    resolver = ExpressionResolver(obj)
    return resolver._resolve(op_ctx.operation)
