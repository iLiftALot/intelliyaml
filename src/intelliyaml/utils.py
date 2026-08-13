from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable, Hashable, Mapping, Sequence
from functools import singledispatchmethod
from typing import Any, ClassVar, Literal, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


# ============================================================================
# Expression-Based Object Resolver
# ============================================================================


type OperationKind = Literal["get", "call", "op", "index", "value", "chain", "expr"]
OpValue = Literal["/", "+", "-", "*", "//", "%", "**", "@", "|", "&"]


class OperationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    debug: bool = Field(default=False, validation_alias=AliasChoices("debug", "_debug"))


class ValueOperation(OperationBase):
    """Literal value operation."""

    value: Any


class GetOperation(OperationBase):
    """Get attribute operation."""

    get: str = Field(validation_alias=AliasChoices("get", "attr"))


class CallOperation(OperationBase):
    """Call method operation."""

    call: str | None = None  # None means call the object itself
    args: tuple[Any, ...] = Field(default_factory=tuple)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class OpOperation(OperationBase):
    """Binary operator operation."""

    op: OpValue
    value: Any = Field(validation_alias=AliasChoices("value", "right"))


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
        operation_types: dict[OperationKind, type[OperationType]] = {
            "get": GetOperation,
            "call": CallOperation,
            "op": OpOperation,
            "index": IndexOperation,
            "value": ValueOperation,
            "chain": ChainOperation,
            "expr": ExpressionOperation,
        }
        expected_type = operation_types[self.kind]

        if not isinstance(self.operation, expected_type):
            raise TypeError(
                f"Operation kind {self.kind!r} requires {expected_type.__name__}, "
                f"got {type(self.operation).__name__}"
            )

        return self


class ExpressionResolver:
    """
    A powerful expression-based resolver for dynamic Python object resolution in YAML files.

    Supports:
        - Attribute access: {"get": "attr_name"}
        - Method calls: {"call": "method_name", "args": [...], "kwargs": {...}}
        - Chained operations: {"chain": [{"get": "attr"}, {"call": "method"}]}
        - Binary operators: {"op": "/", "value": "app.log"} (for path joining, etc.)
        - Indexing: {"index": "key"} or {"index": 0}
        - Direct value: {"value": "literal_value"}

    .. Example::
        .. code:: yaml
        filename: !!python/object:intellipath.LogPath
          chain:
            - get: LOGS
            - op: "/"
              value: "app.log"
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

    @singledispatchmethod
    def _resolve(self, operation: object) -> Any:
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
            - 'LOGS / "app.log"' -> getattr(obj, "LOGS") / "app.log"
            - "method()"       -> obj.method()
            - 'attr.method("x")' -> obj.attr.method("x")
        """
        return ExpressionParser(operation.expr, debug=operation.debug).evaluate(self.obj)

    @_resolve.register(GetOperation)
    def _get(self, operation: GetOperation) -> Any:
        """Attribute access"""
        attr_name = operation.get
        result = getattr(self.obj, attr_name)

        if operation.debug:
            print(f"  getattr({self.obj}, {attr_name!r}) -> {result}")

        return result

    @_resolve.register(CallOperation)
    def _call(self, operation: CallOperation) -> Any:
        """Method/callable invocation"""
        method_name = operation.call
        args = operation.args
        kwargs = operation.kwargs

        if method_name is None:
            if not callable(self.obj):
                raise TypeError(f"Object {self.obj!r} is not callable")
            # Call the object itself
            result = self.obj(*args, **kwargs)
            call_description = repr(self.obj)
        else:
            # Call a method on the object
            method = getattr(self.obj, method_name)
            result = method(*args, **kwargs)
            call_description = f"{self.obj}.{method_name}"

        if operation.debug:
            print(f"  {call_description}(*{args}, **{kwargs}) -> {result}")

        return result

    @_resolve.register(OpOperation)
    def _op(self, operation: OpOperation) -> Any:
        """Binary operator"""
        op_name = operation.op
        value = operation.value
        op_func = self.OPERATORS.get(op_name)

        if op_func is None:
            raise ValueError(f"Unsupported operator: {op_name}")

        result = op_func(self.obj, value)

        if operation.debug:
            print(f"  {self.obj} {op_name} {value} -> {result}")

        return result

    @_resolve.register(IndexOperation)
    def _index(self, operation: IndexOperation) -> Any:
        """Indexing"""
        key = operation.index

        try:
            if isinstance(self.obj, Mapping):
                result = self.obj[key]
            elif isinstance(self.obj, Sequence):
                if not isinstance(key, int):
                    key = self.obj.index(key)
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

    @_resolve.register(ValueOperation)
    def _value(self, operation: ValueOperation) -> Any:
        """Literal value (passthrough)"""
        if operation.debug:
            print(f"  Returning literal value: {operation.value!r}")

        return operation.value


class ExpressionParser:
    """
    Parse and evaluate simple Python-like expressions.

    Grammar (simplified):
        expr     := term (OP term)*
        term     := primary ('.' IDENT | '(' args ')' | '[' key ']')*
        primary  := IDENT | STRING | NUMBER
    """

    # Token patterns
    TOKEN_PATTERN = re.compile(
        r"""
        (?P<STRING>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*') |  # String literals
        (?P<NUMBER>\d+(?:\.\d+)?)           |  # Numbers
        (?P<IDENT>[a-zA-Z_][a-zA-Z0-9_]*)   |  # Identifiers
        (?P<OP>\*\*|//|[+\-*/%|&@])        |  # Operators
        (?P<DOT>\.)                         |  # Dot accessor
        (?P<LPAREN>\()                      |  # Open paren
        (?P<RPAREN>\))                      |  # Close paren
        (?P<LBRACKET>\[)                    |  # Open bracket
        (?P<RBRACKET>\])                    |  # Close bracket
        (?P<COMMA>,)                        |  # Comma
        (?P<WS>\s+)                         |  # Whitespace (ignored)
        (?P<MISMATCH>.)                        # Invalid input
    """,
        re.VERBOSE,
    )

    OPERATOR_PRECEDENCE: ClassVar[dict[OpValue, int]] = {
        "|": 1,
        "&": 2,
        "+": 3,
        "-": 3,
        "*": 4,
        "/": 4,
        "//": 4,
        "%": 4,
        "@": 4,
        "**": 5,
    }

    def __init__(self, expr: str, debug: bool = False) -> None:
        self.expr = expr
        self.debug = debug
        self.tokens = self._tokenize(expr)
        self.pos = 0

    def _tokenize(self, expr: str) -> list[tuple[str, str]]:
        """Tokenize the expression."""
        tokens: list[tuple[str, str]] = []

        for match in self.TOKEN_PATTERN.finditer(expr):
            kind = match.lastgroup
            value = match.group()

            if kind == "MISMATCH":
                raise SyntaxError(
                    f"Unexpected character {value!r} at position {match.start()}"
                )

            if kind is not None and kind != "WS":
                tokens.append((kind, value))

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

        result = self._parse_expr(obj)
        if token := self._peek():
            raise SyntaxError(f"Unexpected token: {token}")

        return result

    def _parse_expr(self, obj: object, min_precedence: int = 0) -> Any:
        """Parse a binary expression using standard operator precedence."""
        left = self._parse_term(obj)

        while (token := self._peek()) and token[0] == "OP":
            op = token[1]
            op_value = self._as_operator(op)
            precedence = self.OPERATOR_PRECEDENCE[op_value]
            if precedence < min_precedence:
                break

            self._advance()
            next_precedence = precedence if op_value == "**" else precedence + 1
            right = self._parse_expr(obj, next_precedence)
            left = ExpressionResolver.OPERATORS[op_value](left, right)

        return left

    @staticmethod
    def _as_operator(value: str) -> OpValue:
        if value not in ExpressionResolver.OPERATORS:
            raise ValueError(f"Unsupported operator: {value}")
        return value

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

        if token[0] == "STRING":
            value = self._advance()[1]
            return ast.literal_eval(value)

        if token[0] == "NUMBER":
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


def operation_builder(ctx: Mapping[Hashable, Any]) -> Operation:
    """Build an Operation object from a context dictionary."""

    non_string_keys = [key for key in ctx if not isinstance(key, str)]
    if non_string_keys:
        raise ValueError(f"Operation context keys must be strings: {non_string_keys!r}")

    operation_ctx = {key: value for key, value in ctx.items() if isinstance(key, str)}

    op_type_map: dict[OperationKind, type[OperationType]] = {
        "get": GetOperation,
        "call": CallOperation,
        "op": OpOperation,
        "index": IndexOperation,
        "expr": ExpressionOperation,
        "value": ValueOperation,
    }

    primary_keys = [
        key
        for key in ("chain", "get", "attr", "call", "op", "index", "expr")
        if key in operation_ctx
    ]
    if not primary_keys and "value" in operation_ctx:
        primary_keys.append("value")

    if len(primary_keys) != 1:
        raise ValueError(
            "Operation context must contain exactly one operation key; "
            f"got {primary_keys or 'none'}"
        )

    key = primary_keys[0]

    if key == "chain":
        raw_chain = operation_ctx["chain"]
        if not isinstance(raw_chain, Sequence) or isinstance(
            raw_chain, (str, bytes, bytearray)
        ):
            raise ValueError("The 'chain' operation must be a sequence of mappings")

        invalid_steps = [
            index for index, step in enumerate(raw_chain) if not isinstance(step, Mapping)
        ]
        if invalid_steps:
            raise ValueError(
                "Each chain step must be an operation mapping; "
                f"invalid steps: {invalid_steps}"
            )

        chain_ops: list[OperationType] = [
            operation_builder(op_ctx).operation for op_ctx in raw_chain
        ]
        chain_ctx = dict(operation_ctx)
        chain_ctx["chain"] = chain_ops
        return Operation(kind="chain", operation=ChainOperation(**chain_ctx))

    kind_by_key: dict[str, OperationKind] = {
        "get": "get",
        "attr": "get",
        "call": "call",
        "op": "op",
        "index": "index",
        "expr": "expr",
        "value": "value",
    }
    kind = kind_by_key[key]
    operation_type = op_type_map[kind]
    return Operation(kind=kind, operation=operation_type(**operation_ctx))


def resolve_object(ctx: Mapping[Hashable, Any], obj: object) -> Any:
    """Resolve an object based on the provided operation context."""

    op_ctx = operation_builder(ctx)
    resolver = ExpressionResolver(obj)
    return resolver._resolve(op_ctx.operation)
