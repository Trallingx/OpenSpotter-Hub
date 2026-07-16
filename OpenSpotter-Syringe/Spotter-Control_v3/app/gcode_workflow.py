"""Editable, event-driven G-code workflow support.

The workflow is intentionally data-first: Python plans machine events and this
module renders the enabled sections attached to each event. Templates use
``{{ expression }}`` placeholders, for example ``value={{runtime.spot.x:.3f}}``.

Expressions are interpreted from a deliberately small AST whitelist.  Python
``eval`` is never used and attribute access is limited to mapping keys.
"""

from __future__ import annotations

import ast
import copy
import io
import json
import math
import operator
import os
import re
import tempfile
import tokenize
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from .input_configs import (
    CLEANING_FIELDS,
    GLOBAL_FIELDS,
    GRID_FIELDS,
    SPIRAL_FIELDS,
    WASHING_FIELDS,
)
from .runtime_logging import get_logger, log_options


logger = get_logger("workflow")


SCHEMA_VERSION = 1
DEFAULT_WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "config_gcode_workflow.json"
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDER_RE = re.compile(r"{{(.*?)}}", re.DOTALL)
_GLOBAL_SENTINEL = "__workflow_namespace_global__"

# Logical planner events are public workflow extension points.  They are kept
# here (rather than in the editor) so a removed section can always be added
# back from the trigger chooser.
EVENT_TRIGGERS = (
    "job_start",
    "syringe_reload",
    "grid_start",
    "grid_spot_move",
    "grid_row_start",
    "grid_spot_dispense",
    "spiral_start",
    "spiral_drop",
    "spiral_continuous",
    "cleaning_start",
    "cleaning_spot_move",
    "cleaning_row_start",
    "cleaning_spot_dispense",
    "washing_start",
    "washing_cycle",
    "washing_end",
    "syringe_empty_start",
    "rinse_cycle",
    "rinse_midpoint",
    "syringe_empty_end",
    "job_end",
)

_GRID_SPOT_TRIGGERS = {
    "grid_spot_move",
    "grid_row_start",
    "grid_spot_dispense",
    "cleaning_spot_move",
    "cleaning_row_start",
    "cleaning_spot_dispense",
}
_SPIRAL_SPOT_TRIGGERS = {"spiral_drop", "spiral_continuous"}
_ALL_SPOT_TRIGGERS = _GRID_SPOT_TRIGGERS | _SPIRAL_SPOT_TRIGGERS

# A trailing dot denotes a namespace prefix; other entries match one exact
# public variable.  Exact spot fields are intentionally listed separately so
# a spiral-only value can never validate in a grid event and quietly render a
# neutral preview default.
_VARIABLE_TRIGGER_SCOPES = {
    "cleaning.cycle": {
        "cleaning_start",
        "cleaning_spot_move",
        "cleaning_row_start",
        "cleaning_spot_dispense",
    },
    "container.": {
        "syringe_reload",
        "syringe_empty_start",
        "rinse_cycle",
        "rinse_midpoint",
        "syringe_empty_end",
    },
    "runtime.spot.start_index": _SPIRAL_SPOT_TRIGGERS,
    "runtime.spot.dispense_ul": _SPIRAL_SPOT_TRIGGERS,
    "runtime.spot.segment_length": _SPIRAL_SPOT_TRIGGERS,
    "runtime.spot.theta": _SPIRAL_SPOT_TRIGGERS,
    "runtime.spot.radius": _SPIRAL_SPOT_TRIGGERS,
    "runtime.spot.continuous": _SPIRAL_SPOT_TRIGGERS,
    "runtime.spot.row": _GRID_SPOT_TRIGGERS,
    "runtime.spot.column": _GRID_SPOT_TRIGGERS,
    "runtime.spot.is_row_start": _GRID_SPOT_TRIGGERS,
    "runtime.spot.": _ALL_SPOT_TRIGGERS,
    "runtime.refill.": {"syringe_reload"},
    "runtime.washing.": {"washing_start", "washing_cycle", "washing_end"},
    "runtime.rinse.": {
        "syringe_empty_start",
        "rinse_cycle",
        "rinse_midpoint",
        "syringe_empty_end",
    },
}

# Job-kind metadata is advisory rather than a hard validation boundary: shared
# events such as job_start can safely use a mode-specific value when guarded by
# runtime.job.kind.  The editor surfaces this information next to event scope.
_VARIABLE_JOB_KIND_SCOPES = {
    "grid.": {"grid"},
    "cleaning.": {"grid"},
    "washing.": {"grid"},
    "spiral.": {"spiral"},
    "runtime.spot.start_index": {"spiral"},
    "runtime.spot.dispense_ul": {"spiral"},
    "runtime.spot.segment_length": {"spiral"},
    "runtime.spot.theta": {"spiral"},
    "runtime.spot.radius": {"spiral"},
    "runtime.spot.continuous": {"spiral"},
    "runtime.spot.row": {"grid"},
    "runtime.spot.column": {"grid"},
    "runtime.spot.is_row_start": {"grid"},
    "runtime.spot.": {"grid", "spiral"},
    "runtime.washing.": {"grid"},
}
_REQUIRED_PLANNER_VARIABLES = {
    "syringe_mm_per_ul",
    "spiral_resolution_radians",
}


class WorkflowError(Exception):
    """Base exception for workflow errors."""


class WorkflowValidationError(WorkflowError):
    """Raised when workflow data does not match the supported schema."""

    def __init__(self, errors: str | list[str]):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


class ExpressionError(WorkflowError):
    """Raised for an invalid or unsupported expression."""


class UndefinedVariableError(ExpressionError):
    """Raised when an expression references a missing context value."""


class TemplateRenderError(WorkflowError):
    """Raised when a template placeholder cannot be rendered."""


class CustomVariableCycleError(WorkflowValidationError, ExpressionError):
    """Raised when custom variable expressions contain a dependency cycle."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}
_COMPARISON_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_SAFE_FUNCTIONS = {
    "min": min,
    "max": max,
    "round": round,
    "abs": abs,
}


@lru_cache(maxsize=2048)
def _rewrite_reserved_names(expression: str) -> str:
    """Rewrite the public ``global`` namespace so Python can parse it."""
    try:
        tokens = []
        for token in tokenize.generate_tokens(io.StringIO(expression).readline):
            if token.type == tokenize.NAME and token.string == "global":
                token = tokenize.TokenInfo(
                    token.type,
                    _GLOBAL_SENTINEL,
                    token.start,
                    token.end,
                    token.line,
                )
            tokens.append(token)
        return tokenize.untokenize(tokens)
    except (IndentationError, tokenize.TokenError) as exc:
        raise ExpressionError(f"Invalid expression syntax: {exc}") from exc


class SafeExpressionEvaluator:
    """Evaluate arithmetic and Boolean expressions against mapping namespaces."""

    max_expression_length = 2000

    def parse(self, expression: str) -> ast.Expression:
        if not isinstance(expression, str) or not expression.strip():
            raise ExpressionError("Expression must be a non-empty string")
        if len(expression) > self.max_expression_length:
            raise ExpressionError("Expression is too long")
        return self._parse_cached(expression.strip())

    @lru_cache(maxsize=4096)
    def _parse_cached(self, expression: str) -> ast.Expression:
        rewritten = _rewrite_reserved_names(expression)
        try:
            tree = ast.parse(rewritten, mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"Invalid expression syntax: {exc.msg}") from exc
        self._validate_node(tree.body)
        return tree

    def validate(self, expression: str) -> None:
        self.parse(expression)

    def evaluate(self, expression: str, context: Mapping[str, Any] | None = None) -> Any:
        tree = self.parse(expression)
        namespaces = dict(context or {})
        if "global" in namespaces:
            namespaces[_GLOBAL_SENTINEL] = namespaces["global"]
        return self._evaluate_node(tree.body, namespaces)

    def _validate_node(self, node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise ExpressionError(f"Unsupported literal: {type(node.value).__name__}")
            return
        if isinstance(node, ast.Name):
            if node.id.startswith("_") and node.id != _GLOBAL_SENTINEL:
                raise ExpressionError("Private names are not available")
            return
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ExpressionError("Private attributes are not available")
            self._validate_node(node.value)
            return
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            self._validate_node(node.left)
            self._validate_node(node.right)
            return
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            self._validate_node(node.operand)
            return
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for value in node.values:
                self._validate_node(value)
            return
        if isinstance(node, ast.Compare):
            if not all(type(op) in _COMPARISON_OPERATORS for op in node.ops):
                raise ExpressionError("Unsupported comparison operator")
            self._validate_node(node.left)
            for comparator in node.comparators:
                self._validate_node(comparator)
            return
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTIONS:
                raise ExpressionError("Only min, max, round, and abs calls are available")
            if node.keywords:
                raise ExpressionError("Keyword arguments are not available")
            for argument in node.args:
                self._validate_node(argument)
            return
        raise ExpressionError(f"Unsupported expression element: {type(node).__name__}")

    def _evaluate_node(self, node: ast.AST, context: Mapping[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in context:
                public_name = "global" if node.id == _GLOBAL_SENTINEL else node.id
                raise UndefinedVariableError(f"Unknown variable: {public_name}")
            return context[node.id]
        if isinstance(node, ast.Attribute):
            parent = self._evaluate_node(node.value, context)
            if not isinstance(parent, Mapping) or node.attr not in parent:
                raise UndefinedVariableError(f"Unknown variable: {self._public_path(node)}")
            return parent[node.attr]
        if isinstance(node, ast.BinOp):
            left = self._evaluate_node(node.left, context)
            right = self._evaluate_node(node.right, context)
            if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 1000:
                raise ExpressionError("Exponent is outside the safe range")
            try:
                result = _BINARY_OPERATORS[type(node.op)](left, right)
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise ExpressionError(str(exc)) from exc
            self._check_result(result)
            return result
        if isinstance(node, ast.UnaryOp):
            try:
                result = _UNARY_OPERATORS[type(node.op)](
                    self._evaluate_node(node.operand, context)
                )
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise ExpressionError(str(exc)) from exc
            self._check_result(result)
            return result
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result = self._evaluate_node(node.values[0], context)
                for value in node.values[1:]:
                    if not result:
                        return result
                    result = self._evaluate_node(value, context)
                return result
            result = self._evaluate_node(node.values[0], context)
            for value in node.values[1:]:
                if result:
                    return result
                result = self._evaluate_node(value, context)
            return result
        if isinstance(node, ast.Compare):
            left = self._evaluate_node(node.left, context)
            for operation, comparator in zip(node.ops, node.comparators):
                right = self._evaluate_node(comparator, context)
                try:
                    matches = _COMPARISON_OPERATORS[type(operation)](left, right)
                except (TypeError, ValueError) as exc:
                    raise ExpressionError(str(exc)) from exc
                if not matches:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            arguments = [self._evaluate_node(arg, context) for arg in node.args]
            try:
                result = _SAFE_FUNCTIONS[node.func.id](*arguments)
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise ExpressionError(str(exc)) from exc
            self._check_result(result)
            return result
        raise ExpressionError(f"Unsupported expression element: {type(node).__name__}")

    @staticmethod
    def _check_result(value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ExpressionError("Expression produced a non-finite number")
        if isinstance(value, str) and len(value) > 100_000:
            raise ExpressionError("Expression produced an excessively long string")

    @staticmethod
    def _public_path(node: ast.AST) -> str:
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append("global" if current.id == _GLOBAL_SENTINEL else current.id)
        return ".".join(reversed(parts))


_EVALUATOR = SafeExpressionEvaluator()


@lru_cache(maxsize=4096)
def _split_placeholder(contents: str) -> tuple[str, str | None]:
    """Split ``expression:format`` at a top-level colon."""
    text = contents.strip()
    quote = None
    escaped = False
    depth = 0
    colons = []
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if quote:
            if character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in ("'", '"'):
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == ":" and depth == 0:
            colons.append(index)
    for index in reversed(colons):
        expression = text[:index].strip()
        format_spec = text[index + 1 :].strip()
        if expression and format_spec:
            try:
                _EVALUATOR.validate(expression)
                return expression, format_spec
            except ExpressionError:
                pass
    _EVALUATOR.validate(text)
    return text, None


@lru_cache(maxsize=2048)
def _compile_template(
    template: str,
) -> tuple[tuple[tuple[str, str, str | None], ...], str]:
    """Compile a template into immutable literal/expression segments."""
    segments = []
    cursor = 0
    matches = tuple(_PLACEHOLDER_RE.finditer(template))
    for match in matches:
        try:
            expression, format_spec = _split_placeholder(match.group(1))
        except ExpressionError as exc:
            raise TemplateRenderError(str(exc)) from exc
        segments.append(
            (
                template[cursor : match.start()],
                expression,
                format_spec,
            )
        )
        cursor = match.end()
    if template.count("{{") != len(matches) or template.count("}}") != len(matches):
        raise TemplateRenderError("Template contains unmatched placeholder braces")
    return tuple(segments), template[cursor:]


def template_expressions(template: str) -> list[tuple[str, str | None]]:
    if not isinstance(template, str):
        raise TemplateRenderError("Template must be a string")
    segments, _trailing_literal = _compile_template(template)
    return [
        (expression, format_spec)
        for _literal, expression, format_spec in segments
    ]


def render_template(template: str, context: Mapping[str, Any] | None = None) -> str:
    """Render all safe-expression placeholders in *template*."""
    if not isinstance(template, str):
        raise TemplateRenderError("Template must be a string")
    segments, trailing_literal = _compile_template(template)
    render_context = context or {}
    output = []
    for literal, expression, format_spec in segments:
        output.append(literal)
        try:
            value = _EVALUATOR.evaluate(expression, render_context)
            if format_spec is not None:
                if not isinstance(value, (int, float, bool)):
                    raise TemplateRenderError(
                        f"Numeric format '{format_spec}' requires a number"
                    )
                rendered = format(value, format_spec)
            elif value is None:
                rendered = ""
            elif not isinstance(value, (str, int, float, bool)):
                raise TemplateRenderError(
                    f"Expression '{expression}' produced unsupported {type(value).__name__}"
                )
            elif isinstance(value, float):
                if not math.isfinite(value):
                    raise TemplateRenderError(
                        f"Expression '{expression}' produced a non-finite number"
                    )
                decimal_value = Decimal(str(value))
                rendered = (
                    "0"
                    if decimal_value == 0
                    else format(decimal_value, "f")
                )
            else:
                rendered = str(value)
        except (ExpressionError, ValueError) as exc:
            raise TemplateRenderError(f"Cannot render '{expression}': {exc}") from exc
        output.append(rendered)
    output.append(trailing_literal)
    return "".join(output)


@lru_cache(maxsize=4096)
def _custom_dependencies_cached(expression: str) -> frozenset[str]:
    tree = _EVALUATOR.parse(expression)
    dependencies = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "custom":
                dependencies.add(node.attr)
    return frozenset(dependencies)


def _custom_dependencies(expression: str) -> set[str]:
    return set(_custom_dependencies_cached(expression))


@lru_cache(maxsize=4096)
def _expression_variable_paths_cached(expression: str) -> frozenset[str]:
    """Return the public leaf-variable paths referenced by an expression."""
    tree = _EVALUATOR.parse(expression)
    nested_attributes = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
    }
    call_names = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attribute_names = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    paths = {
        _EVALUATOR._public_path(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and id(node) not in nested_attributes
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name):
            continue
        if id(node) in call_names or id(node) in attribute_names:
            continue
        paths.add("global" if node.id == _GLOBAL_SENTINEL else node.id)
    return frozenset(paths)


def _expression_variable_paths(expression: str) -> set[str]:
    return set(_expression_variable_paths_cached(expression))


def _known_variable_names(custom_names: set[str]) -> set[str]:
    names = {
        f"{namespace}.{field.key}"
        for namespace, fields, _source in _FIELD_GROUPS
        for field in fields
    }
    names.update(item[0] for item in _DERIVED_VARIABLES)
    names.update(f"custom.{name}" for name in custom_names)
    return names


def _expand_custom_paths(
    paths: set[str], custom_variables: list[Mapping[str, Any]]
) -> set[str]:
    expressions = {
        variable["name"]: variable.get("expression")
        for variable in custom_variables
        if isinstance(variable, Mapping) and isinstance(variable.get("name"), str)
    }

    def expand(path: str, visiting: set[str]) -> set[str]:
        if not path.startswith("custom."):
            return {path}
        name = path.split(".", 1)[1]
        expression = expressions.get(name)
        if not isinstance(expression, str) or name in visiting:
            return set()
        return {
            expanded
            for dependency in _expression_variable_paths(expression)
            for expanded in expand(dependency, visiting | {name})
        }

    return {
        expanded
        for path in paths
        for expanded in expand(path, set())
    }


def _matches_scope_pattern(path: str, pattern: str) -> bool:
    return path.startswith(pattern) if pattern.endswith(".") else path == pattern


def _allowed_triggers_for_path(path: str):
    for pattern, triggers in _VARIABLE_TRIGGER_SCOPES.items():
        if _matches_scope_pattern(path, pattern):
            return triggers
    return None


def _job_kinds_for_path(path: str):
    for pattern, job_kinds in _VARIABLE_JOB_KIND_SCOPES.items():
        if _matches_scope_pattern(path, pattern):
            return job_kinds
    return None


def _validate_custom_value(name: str, variable_type: str, value: Any) -> None:
    """Enforce declared custom-variable types and finite machine numerics."""
    if variable_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif variable_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif variable_type == "boolean":
        valid = isinstance(value, bool)
    elif variable_type == "string":
        valid = isinstance(value, str)
    else:
        raise WorkflowValidationError(
            f"Custom variable '{name}' has unsupported type '{variable_type}'"
        )
    if not valid:
        raise WorkflowValidationError(
            f"Custom variable '{name}' must resolve to {variable_type}, got {type(value).__name__}"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise WorkflowValidationError(
            f"Custom variable '{name}' must be a finite number"
        )


def _resolve_custom_variables(
    definitions: list[Mapping[str, Any]],
    context: Mapping[str, Any],
    requested_names: Any = None,
    *,
    definition_index: Mapping[str, Mapping[str, Any]] | None = None,
    dependency_index: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, Any]:
    by_name = (
        {definition["name"]: definition for definition in definitions}
        if definition_index is None
        else definition_index
    )
    external = context.get("custom", {})
    if not isinstance(external, Mapping):
        raise ExpressionError("The custom context namespace must be a mapping")
    resolved = dict(external)
    visiting: list[str] = []

    def resolve(name: str) -> Any:
        if name in resolved and name not in by_name:
            return resolved[name]
        if name in resolved and name in by_name:
            return resolved[name]
        if name in visiting:
            cycle = visiting[visiting.index(name) :] + [name]
            raise CustomVariableCycleError(
                "Custom variable cycle: " + " -> ".join(cycle)
            )
        if name not in by_name:
            raise UndefinedVariableError(f"Unknown variable: custom.{name}")
        visiting.append(name)
        definition = by_name[name]
        if "expression" in definition:
            expression = definition["expression"]
            dependencies = (
                None
                if dependency_index is None
                else dependency_index.get(name)
            )
            if dependencies is None:
                dependencies = _custom_dependencies_cached(expression)
            for dependency in dependencies:
                if dependency in by_name:
                    resolve(dependency)
            local_context = dict(context)
            local_context["custom"] = dict(resolved)
            value = _EVALUATOR.evaluate(expression, local_context)
        else:
            value = copy.deepcopy(definition.get("value"))
        _validate_custom_value(name, definition.get("type", "number"), value)
        visiting.pop()
        resolved[name] = value
        return value

    names_to_resolve = by_name if requested_names is None else requested_names
    for variable_name in names_to_resolve:
        resolve(variable_name)
    return resolved


def validate_workflow(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a detached workflow copy.

    The copy is convenient for editors: callers can stage mutations without
    changing the object currently used by a renderer.
    """
    errors: list[str] = []
    if not isinstance(workflow, Mapping):
        raise WorkflowValidationError("Workflow must be a JSON object")
    candidate = copy.deepcopy(dict(workflow))
    if candidate.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION}, got {candidate.get('schema_version')!r}"
        )
    if not isinstance(candidate.get("name", ""), str):
        errors.append("name must be a string")

    custom_variables = candidate.get("custom_variables", [])
    if not isinstance(custom_variables, list):
        errors.append("custom_variables must be a list")
        custom_variables = []
    custom_names = set()
    for index, variable in enumerate(custom_variables):
        prefix = f"custom_variables[{index}]"
        if not isinstance(variable, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        name = variable.get("name")
        if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
            errors.append(f"{prefix}.name must be a valid identifier")
        elif name in custom_names:
            errors.append(f"Duplicate custom variable name: {name}")
        else:
            custom_names.add(name)
        has_value = "value" in variable
        has_expression = "expression" in variable
        variable_type = variable.get("type")
        if variable_type not in ("number", "integer", "boolean", "string"):
            errors.append(
                f"{prefix}.type must be number, integer, boolean, or string"
            )
        for metadata_key in ("label", "unit", "description"):
            if metadata_key in variable and not isinstance(variable[metadata_key], str):
                errors.append(f"{prefix}.{metadata_key} must be a string")
        if has_value == has_expression:
            errors.append(f"{prefix} must define exactly one of value or expression")
        if has_expression:
            if not isinstance(variable["expression"], str):
                errors.append(f"{prefix}.expression must be a string")
            else:
                try:
                    _EVALUATOR.validate(variable["expression"])
                except ExpressionError as exc:
                    errors.append(f"{prefix}.expression: {exc}")
        elif has_value and variable_type in ("number", "integer", "boolean", "string"):
            try:
                _validate_custom_value(str(name), variable_type, variable["value"])
            except WorkflowValidationError as exc:
                errors.extend(f"{prefix}: {message}" for message in exc.errors)

    known_variables = _known_variable_names(custom_names)
    for required_name in sorted(_REQUIRED_PLANNER_VARIABLES - custom_names):
        errors.append(f"Missing required planner variable: custom.{required_name}")
    for index, variable in enumerate(custom_variables):
        expression = variable.get("expression") if isinstance(variable, Mapping) else None
        if not isinstance(expression, str):
            continue
        try:
            unknown = _expression_variable_paths(expression) - known_variables
        except ExpressionError:
            continue
        for variable_name in sorted(unknown):
            errors.append(
                f"custom_variables[{index}].expression references unknown variable '{variable_name}'"
            )
    for required_name in sorted(_REQUIRED_PLANNER_VARIABLES & custom_names):
        definition = next(
            variable
            for variable in custom_variables
            if isinstance(variable, Mapping) and variable.get("name") == required_name
        )
        if definition.get("type") not in ("number", "integer"):
            errors.append(f"custom.{required_name} must be numeric")
        try:
            planner_paths = _expand_custom_paths(
                {f"custom.{required_name}"}, custom_variables
            )
        except ExpressionError:
            planner_paths = set()
        for variable_name in sorted(planner_paths):
            if _allowed_triggers_for_path(variable_name) is not None:
                errors.append(
                    f"custom.{required_name} cannot depend on event-scoped variable '{variable_name}'"
                )

    # Detect cycles statically, without requiring generation context values.
    dependencies = {}
    for variable in custom_variables:
        if isinstance(variable, Mapping) and isinstance(variable.get("name"), str):
            if isinstance(variable.get("expression"), str):
                try:
                    dependencies[variable["name"]] = _custom_dependencies(
                        variable["expression"]
                    ) & custom_names
                except ExpressionError:
                    dependencies[variable["name"]] = set()
            else:
                dependencies[variable["name"]] = set()
    visiting = set()
    visited = set()

    def visit(name: str, path: list[str]) -> None:
        if name in visited:
            return
        if name in visiting:
            cycle = path[path.index(name) :]
            raise CustomVariableCycleError(
                "Custom variable cycle: " + " -> ".join(cycle)
            )
        visiting.add(name)
        for dependency in dependencies.get(name, set()):
            visit(dependency, path + [dependency])
        visiting.remove(name)
        visited.add(name)

    for custom_name in dependencies:
        visit(custom_name, [custom_name])

    # Planner conversion factors are configuration, not event state.  Resolve
    # them against the complete field defaults so invalid literal values and
    # context-independent expressions are rejected when the editor saves,
    # before any output file is opened.
    for required_name in sorted(_REQUIRED_PLANNER_VARIABLES & custom_names):
        try:
            resolved_value = _resolve_custom_variables(
                custom_variables,
                build_runtime_context_defaults(),
                (required_name,),
            )[required_name]
        except WorkflowError as exc:
            errors.append(f"custom.{required_name} cannot be resolved: {exc}")
            continue
        if (
            not isinstance(resolved_value, (int, float))
            or isinstance(resolved_value, bool)
            or not math.isfinite(float(resolved_value))
            or float(resolved_value) <= 0
        ):
            errors.append(f"custom.{required_name} must resolve to a positive number")

    blocks = candidate.get("blocks")
    if not isinstance(blocks, list):
        errors.append("blocks must be a list")
        blocks = []
    block_ids = set()
    section_ids = set()
    for block_index, block in enumerate(blocks):
        prefix = f"blocks[{block_index}]"
        if not isinstance(block, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        for key in ("id", "name", "role"):
            if not isinstance(block.get(key), str) or not block.get(key):
                errors.append(f"{prefix}.{key} must be a non-empty string")
        block_id = block.get("id")
        if block_id in block_ids:
            errors.append(f"Duplicate block id: {block_id}")
        block_ids.add(block_id)
        if not isinstance(block.get("enabled"), bool):
            errors.append(f"{prefix}.enabled must be a Boolean")
        sections = block.get("sections")
        if not isinstance(sections, list):
            errors.append(f"{prefix}.sections must be a list")
            continue
        for section_index, section in enumerate(sections):
            section_prefix = f"{prefix}.sections[{section_index}]"
            if not isinstance(section, Mapping):
                errors.append(f"{section_prefix} must be an object")
                continue
            for key in ("id", "name", "trigger"):
                if not isinstance(section.get(key), str) or not section.get(key):
                    errors.append(f"{section_prefix}.{key} must be a non-empty string")
            if not isinstance(section.get("template"), str):
                errors.append(f"{section_prefix}.template must be a string")
            section_id = section.get("id")
            section_references = set()
            if section_id in section_ids:
                errors.append(f"Duplicate section id: {section_id}")
            section_ids.add(section_id)
            trigger = section.get("trigger")
            if isinstance(trigger, str) and trigger and trigger not in EVENT_TRIGGERS:
                errors.append(
                    f"{section_prefix}.trigger is not a supported planner event: {trigger}"
                )
            if isinstance(section.get("template"), str):
                try:
                    expressions = template_expressions(section["template"])
                    for expression, _format_spec in expressions:
                        references = _expression_variable_paths(expression)
                        section_references.update(references)
                        for variable_name in sorted(
                            references - known_variables
                        ):
                            errors.append(
                                f"{section_prefix}.template references unknown variable '{variable_name}'"
                            )
                except TemplateRenderError as exc:
                    errors.append(f"{section_prefix}.template: {exc}")
            if "condition" in section:
                if not isinstance(section["condition"], str):
                    errors.append(f"{section_prefix}.condition must be a string")
                elif section["condition"].strip():
                    try:
                        _EVALUATOR.validate(section["condition"])
                        references = _expression_variable_paths(section["condition"])
                        section_references.update(references)
                        for variable_name in sorted(
                            references - known_variables
                        ):
                            errors.append(
                                f"{section_prefix}.condition references unknown variable '{variable_name}'"
                            )
                    except ExpressionError as exc:
                        errors.append(f"{section_prefix}.condition: {exc}")
            if isinstance(trigger, str) and trigger in EVENT_TRIGGERS:
                for variable_name in sorted(
                    _expand_custom_paths(section_references, custom_variables)
                ):
                    allowed_triggers = _allowed_triggers_for_path(variable_name)
                    if allowed_triggers is not None and trigger not in allowed_triggers:
                        errors.append(
                            f"{section_prefix} uses '{variable_name}' outside its event scope"
                        )

    if errors:
        raise WorkflowValidationError(errors)
    return candidate


def load_workflow(path: str | os.PathLike[str] = DEFAULT_WORKFLOW_PATH) -> dict[str, Any]:
    workflow_path = Path(path)
    try:
        with workflow_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowValidationError(f"Cannot load workflow {workflow_path}: {exc}") from exc
    return validate_workflow(payload)


def default_workflow() -> dict[str, Any]:
    """Return a detached copy of the shipped editable workflow."""
    return load_workflow(DEFAULT_WORKFLOW_PATH)


def save_workflow(
    workflow: Mapping[str, Any],
    path: str | os.PathLike[str] = DEFAULT_WORKFLOW_PATH,
) -> Path:
    """Validate and atomically save a workflow JSON document."""
    payload = validate_workflow(workflow)
    workflow_path = Path(path)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(workflow_path.parent),
        prefix=f".{workflow_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, workflow_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return workflow_path


class WorkflowStore:
    """Small persistence facade used by the runtime editor."""

    def __init__(self, path: str | os.PathLike[str] = DEFAULT_WORKFLOW_PATH):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        workflow = load_workflow(self.path)
        log_options(logger, "workflow.loaded", path=self.path, workflow=workflow)
        return workflow

    def save(self, workflow: Mapping[str, Any]) -> Path:
        try:
            destination = save_workflow(workflow, self.path)
        except Exception:
            logger.exception("workflow.save_failed | path=%s", self.path)
            raise
        log_options(
            logger,
            "workflow.persisted",
            path=destination,
            workflow=workflow,
        )
        return destination

    def validate(self, workflow: Mapping[str, Any]) -> dict[str, Any]:
        return validate_workflow(workflow)


def _deep_merge(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def build_runtime_context_defaults() -> dict[str, Any]:
    """Return a complete neutral context for previews and event expressions.

    Planners replace these values with live data for the active event.  Keeping
    the full shape available lets custom expressions reference event variables
    while the engine is being constructed and lets the editor preview every
    shipped trigger without inventing machine commands.
    """
    context: dict[str, Any] = {}
    for namespace, fields, _source in _FIELD_GROUPS:
        context[namespace] = {
            field.key: copy.deepcopy(field.default)
            for field in fields
        }
    context["grid"].update({"name": "Grid", "color": "green"})
    context["cleaning"].update({"cycle": 0})
    context["spiral"].update({"name": "Spiral", "color": "orange"})
    context.update({
        "acceptance": {
            "x_left": 0.0,
            "x_right": 0.0,
            "y_bottom": 0.0,
            "y_top": 0.0,
        },
        "container": {"id": 0, "x": 0.0, "y": 0.0, "z": 0.0},
        "runtime": {
            "job": {"kind": "preview", "pattern_index": 0},
            "spot": {
                "index": 0,
                "start_index": 0,
                "row": 0,
                "column": 0,
                "x": 0.0,
                "y": 0.0,
                "dispense_mm": 0.0,
                "dispense_ul": 0.0,
                "segment_length": 0.0,
                "theta": 0.0,
                "radius": 0.0,
                "continuous": False,
                "is_row_start": True,
            },
            "refill": {
                "reason": "preview",
                "dynamic": False,
                "container_id": 0,
                "fill_mm": 0.0,
                "priming_mm": 0.0,
                "target_fill_mm": 0.0,
                "target_fill_ul": 0.0,
                "remaining_spots_mm": 0.0,
                "cleaning_mm": 0.0,
                "reserve_mm": 0.0,
                "total_needed_mm": 0.0,
                "cap_mm": 0.0,
            },
            "washing": {"cycle": 0, "x_start": 0.0, "x_end": 0.0},
            "rinse": {"cycle": 0, "phase": 0, "max_mm": 0.0, "min_mm": 0.0},
        },
    })
    return context


class WorkflowEngine:
    """Render enabled workflow sections for planner events."""

    def __init__(
        self,
        workflow_or_path: Mapping[str, Any] | str | os.PathLike[str] | None = None,
        base_context: Mapping[str, Any] | None = None,
    ):
        if workflow_or_path is None:
            workflow = load_workflow(DEFAULT_WORKFLOW_PATH)
        elif isinstance(workflow_or_path, Mapping):
            workflow = validate_workflow(workflow_or_path)
        else:
            workflow = load_workflow(workflow_or_path)
        self.workflow = workflow
        self.base_context = copy.deepcopy(dict(base_context or {}))
        self._last_context = copy.deepcopy(self.base_context)
        self._last_custom_values = {}
        self._custom_definitions = self.workflow.get("custom_variables", [])
        self._custom_definition_index = {
            definition["name"]: definition
            for definition in self._custom_definitions
        }
        self._custom_dependency_index = {
            name: (
                _custom_dependencies_cached(definition["expression"])
                if "expression" in definition
                else frozenset()
            )
            for name, definition in self._custom_definition_index.items()
        }
        sections_by_trigger: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
        custom_dependencies_by_trigger: dict[str, set[str]] = {}
        for block in self.workflow["blocks"]:
            if not block["enabled"]:
                continue
            for section in block["sections"]:
                trigger = section["trigger"]
                sections_by_trigger.setdefault(trigger, []).append((block, section))
                expressions = [
                    expression
                    for expression, _format_spec in template_expressions(
                        section["template"]
                    )
                ]
                if section.get("condition"):
                    expressions.append(section["condition"])
                requested = custom_dependencies_by_trigger.setdefault(trigger, set())
                for expression in expressions:
                    requested.update(
                        path.split(".", 1)[1]
                        for path in _expression_variable_paths_cached(expression)
                        if path.startswith("custom.")
                    )
        self._sections_by_trigger = {
            trigger: tuple(sections)
            for trigger, sections in sections_by_trigger.items()
        }
        self._custom_dependencies_by_trigger = {
            trigger: frozenset(names)
            for trigger, names in custom_dependencies_by_trigger.items()
        }
        for definition in self._custom_definitions:
            try:
                self._last_custom_values.update(
                    _resolve_custom_variables(
                        self._custom_definitions,
                        self.base_context,
                        (definition["name"],),
                        definition_index=self._custom_definition_index,
                        dependency_index=self._custom_dependency_index,
                    )
                )
            except (ExpressionError, WorkflowValidationError):
                # Event-scoped expressions are resolved when a matching
                # section supplies their runtime context.
                continue

    @property
    def custom_values(self) -> dict[str, Any]:
        return copy.deepcopy(self._last_custom_values)

    def custom_value(self, name: str, context: Mapping[str, Any] | None = None) -> Any:
        """Resolve one custom value without evaluating unrelated definitions."""
        merged = _deep_merge(self.base_context, context or {})
        values = _resolve_custom_variables(
            self._custom_definitions,
            merged,
            (name,),
            definition_index=self._custom_definition_index,
            dependency_index=self._custom_dependency_index,
        )
        self._last_custom_values.update(values)
        return copy.deepcopy(values[name])

    def update_context(self, context: Mapping[str, Any]) -> None:
        """Merge live job state into every subsequent workflow event."""
        self.base_context = _deep_merge(self.base_context, context)
        self._last_context = copy.deepcopy(self.base_context)
        refreshed = {}
        for name in tuple(self._last_custom_values):
            try:
                refreshed.update(
                    _resolve_custom_variables(
                        self._custom_definitions,
                        self.base_context,
                        (name,),
                        definition_index=self._custom_definition_index,
                        dependency_index=self._custom_dependency_index,
                    )
                )
            except (ExpressionError, WorkflowValidationError):
                continue
        self._last_custom_values = refreshed

    def emit(
        self, trigger: str, context: Mapping[str, Any] | None = None
    ) -> str:
        if not isinstance(trigger, str) or not trigger:
            raise WorkflowError("trigger must be a non-empty string")
        merged = _deep_merge(self.base_context, context or {})
        matching_sections = self._sections_by_trigger.get(trigger, ())
        logger.debug(
            "workflow.trigger_evaluated | trigger=%s | matching_sections=%d",
            trigger,
            len(matching_sections),
        )
        requested_custom = self._custom_dependencies_by_trigger.get(
            trigger,
            frozenset(),
        )
        custom_values = _resolve_custom_variables(
            self._custom_definitions,
            merged,
            requested_custom,
            definition_index=self._custom_definition_index,
            dependency_index=self._custom_dependency_index,
        )
        merged["custom"] = custom_values
        output = []
        skipped_conditions = 0
        for block, section in matching_sections:
            condition = section.get("condition")
            if condition and not bool(_EVALUATOR.evaluate(condition, merged)):
                skipped_conditions += 1
                continue
            try:
                output.append(render_template(section["template"], merged))
            except TemplateRenderError as exc:
                raise TemplateRenderError(
                    f"Block '{block['name']}', section '{section['name']}': {exc}"
                ) from exc
        self._last_context = merged
        self._last_custom_values = custom_values
        logger.debug(
            "workflow.trigger_rendered | trigger=%s | rendered_sections=%d | skipped_conditions=%d",
            trigger,
            len(output),
            skipped_conditions,
        )
        return "".join(output)

    render = emit

    def variable_catalog(self) -> list[dict[str, Any]]:
        return build_variable_catalog(self._last_context, self.workflow)


def render_preview(
    workflow: Mapping[str, Any] | str | os.PathLike[str],
    trigger: str,
    context: Mapping[str, Any] | None = None,
) -> str:
    preview_context = _deep_merge(build_runtime_context_defaults(), context or {})
    return WorkflowEngine(workflow, preview_context).emit(trigger)


_FIELD_GROUPS = (
    ("global", GLOBAL_FIELDS, "GLOBAL_FIELDS"),
    ("grid", GRID_FIELDS, "GRID_FIELDS"),
    ("cleaning", CLEANING_FIELDS, "CLEANING_FIELDS"),
    ("washing", WASHING_FIELDS, "WASHING_FIELDS"),
    ("spiral", SPIRAL_FIELDS, "SPIRAL_FIELDS"),
)

_DERIVED_VARIABLES = (
    ("acceptance.x_left", "Acceptance left", "number", "mm", "Computed acceptance-square left edge"),
    ("acceptance.x_right", "Acceptance right", "number", "mm", "Computed acceptance-square right edge"),
    ("acceptance.y_bottom", "Acceptance bottom", "number", "mm", "Computed acceptance-square bottom edge"),
    ("acceptance.y_top", "Acceptance top", "number", "mm", "Computed acceptance-square top edge"),
    ("container.id", "Container number", "integer", "", "Active loading or emptying container"),
    ("container.x", "Container X", "number", "mm", "Active container X coordinate"),
    ("container.y", "Container Y", "number", "mm", "Active container Y coordinate"),
    ("container.z", "Container fill Z", "number", "mm", "Active container fill height"),
    ("grid.name", "Grid name", "string", "", "Current grid display name"),
    ("grid.color", "Grid color", "string", "", "Current grid display color"),
    ("cleaning.cycle", "Cleaning cycle", "integer", "", "Zero-based cleaning-grid cycle"),
    ("spiral.name", "Spiral name", "string", "", "Current spiral display name"),
    ("spiral.color", "Spiral color", "string", "", "Current spiral display color"),
    ("runtime.job.kind", "Job kind", "string", "", "Grid, spiral, or preview job"),
    ("runtime.job.pattern_index", "Pattern index", "integer", "", "One-based active pattern index"),
    ("runtime.spot.index", "Spot index", "integer", "", "Zero-based spot index"),
    ("runtime.spot.start_index", "Spiral start", "integer", "", "Zero-based multi-start spiral index"),
    ("runtime.spot.row", "Spot row", "integer", "", "Zero-based row index"),
    ("runtime.spot.column", "Spot column", "integer", "", "Zero-based column index"),
    ("runtime.spot.x", "Spot X", "number", "mm", "Planned spot X coordinate"),
    ("runtime.spot.y", "Spot Y", "number", "mm", "Planned spot Y coordinate"),
    ("runtime.spot.dispense_mm", "Spot dispense", "number", "mm", "Plunger travel for this spot"),
    ("runtime.spot.dispense_ul", "Spot volume", "number", "uL", "Liquid volume for the current spiral point"),
    ("runtime.spot.segment_length", "Segment length", "number", "mm", "Current spiral segment length"),
    ("runtime.spot.theta", "Spiral angle", "number", "rad", "Current spiral angular position"),
    ("runtime.spot.radius", "Spiral radius", "number", "mm", "Current spiral radius"),
    ("runtime.spot.continuous", "Continuous segment", "boolean", "", "Whether the current spiral point is a continuous segment"),
    ("runtime.spot.is_row_start", "Row start", "boolean", "", "Whether this spot starts a row"),
    ("runtime.refill.reason", "Refill reason", "string", "", "Why a refill was planned"),
    ("runtime.refill.dynamic", "Dynamic refill", "boolean", "", "Whether to include dynamic refill diagnostics"),
    ("runtime.refill.container_id", "Refill container", "integer", "", "Selected loading container number"),
    ("runtime.refill.fill_mm", "Aspirated travel", "number", "mm", "Fill plus priming plunger travel"),
    ("runtime.refill.priming_mm", "Priming travel", "number", "mm", "Priming plunger travel"),
    ("runtime.refill.target_fill_mm", "Target fill", "number", "mm", "Useful target plunger travel"),
    ("runtime.refill.target_fill_ul", "Target fill", "number", "uL", "Useful target volume"),
    ("runtime.refill.remaining_spots_mm", "Remaining spots", "number", "mm", "Remaining grid plunger demand"),
    ("runtime.refill.cleaning_mm", "Cleaning demand", "number", "mm", "Reserved cleaning demand"),
    ("runtime.refill.reserve_mm", "Reserve", "number", "mm", "Reserved plunger travel"),
    ("runtime.refill.total_needed_mm", "Total required", "number", "mm", "Total calculated plunger demand"),
    ("runtime.refill.cap_mm", "Refill cap", "number", "mm", "Maximum permitted refill"),
    ("runtime.washing.cycle", "Wash cycle", "integer", "", "Zero-based washing cycle"),
    ("runtime.washing.x_start", "Wash X start", "number", "mm", "Washing stroke start"),
    ("runtime.washing.x_end", "Wash X end", "number", "mm", "Washing stroke end"),
    ("runtime.rinse.cycle", "Rinse cycle", "integer", "", "Rinse cycle number, zero when disabled"),
    ("runtime.rinse.phase", "Rinse phase", "integer", "", "First or second rinse pass"),
    ("runtime.rinse.max_mm", "Rinse aspiration", "number", "mm", "Rinse aspiration endpoint"),
    ("runtime.rinse.min_mm", "Rinse dispense", "number", "mm", "Rinse dispense endpoint"),
)


def _infer_field_type(field: Any) -> str:
    unit = str(getattr(field, "unit", "")).lower()
    default = getattr(field, "default", None)
    if unit == "bool" or isinstance(default, bool):
        return "boolean"
    if unit == "int" or "int" in unit or isinstance(default, int):
        return "integer"
    if unit == "str" or isinstance(default, str):
        return "string"
    return "number"


def _lookup_path(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _flatten_context(context: Mapping[str, Any], prefix: str = ""):
    for key, value in context.items():
        if not isinstance(key, str):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            yield from _flatten_context(value, path)
        else:
            yield path, value


def build_variable_catalog(
    context: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return metadata for configured, derived, custom, and live variables."""
    live_context = dict(context or {})
    records: dict[str, dict[str, Any]] = {}
    for namespace, fields, source in _FIELD_GROUPS:
        for field in fields:
            name = f"{namespace}.{field.key}"
            job_kinds = _job_kinds_for_path(name)
            records[name] = {
                "name": name,
                "label": field.label,
                "type": _infer_field_type(field),
                "unit": field.unit,
                "source": source,
                "scope": namespace,
                "description": field.label,
                "value": _lookup_path(live_context, name),
                "job_kinds": sorted(job_kinds) if job_kinds else [],
            }
    for name, label, value_type, unit, description in _DERIVED_VARIABLES:
        allowed_triggers = _allowed_triggers_for_path(name)
        job_kinds = _job_kinds_for_path(name)
        records[name] = {
            "name": name,
            "label": label,
            "type": value_type,
            "unit": unit,
            "source": "runtime",
            "scope": name.split(".", 1)[0],
            "description": description,
            "value": _lookup_path(live_context, name),
            "triggers": sorted(allowed_triggers) if allowed_triggers else [],
            "job_kinds": sorted(job_kinds) if job_kinds else [],
        }
    resolved_custom: Mapping[str, Any] = {}
    if workflow:
        try:
            resolved_custom = _resolve_custom_variables(
                workflow.get("custom_variables", []), live_context
            )
        except WorkflowError:
            # The catalog must remain usable while an editor contains an
            # incomplete expression; validation reports the actionable error.
            resolved_custom = {}
        for variable in workflow.get("custom_variables", []):
            name = f"custom.{variable['name']}"
            records[name] = {
                "name": name,
                "label": variable.get("label", variable["name"]),
                "type": variable.get("type", "number"),
                "unit": variable.get("unit", ""),
                "source": "custom expression" if "expression" in variable else "custom value",
                "scope": "custom",
                "description": variable.get("description", "User-defined workflow variable"),
                "value": resolved_custom.get(
                    variable["name"], variable.get("value")
                ),
            }
    for name, value in _flatten_context(live_context):
        if name not in records:
            records[name] = {
                "name": name,
                "label": name,
                "type": (
                    "boolean" if isinstance(value, bool)
                    else "integer" if isinstance(value, int)
                    else "number" if isinstance(value, float)
                    else "string"
                ),
                "unit": "",
                "source": "live context",
                "scope": name.split(".", 1)[0],
                "description": "Runtime-provided value",
                "value": value,
            }
        else:
            records[name]["value"] = value
    return [records[name] for name in sorted(records, key=str.casefold)]


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_WORKFLOW_PATH",
    "WorkflowError",
    "WorkflowValidationError",
    "ExpressionError",
    "UndefinedVariableError",
    "TemplateRenderError",
    "CustomVariableCycleError",
    "SafeExpressionEvaluator",
    "WorkflowStore",
    "WorkflowEngine",
    "validate_workflow",
    "default_workflow",
    "load_workflow",
    "save_workflow",
    "render_template",
    "render_preview",
    "template_expressions",
    "build_variable_catalog",
]
