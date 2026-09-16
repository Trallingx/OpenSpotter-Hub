"""Typed field definitions and widget-value coercion shared across the app."""

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, Sequence, Tuple


TRUE_VALUES = frozenset(("1", "true", "yes", "on"))
FALSE_VALUES = frozenset(("0", "false", "no", "off"))


class FieldInputError(ValueError):
    """Raised when strict parsing finds missing or invalid field values."""


@dataclass(frozen=True)
class Field:
    """Declarative input field used by UI forms, profiles, and plugins.

    ``widget`` and ``choices`` are optional presentation hints. Keeping them
    on the field lets plugins describe their own controls without teaching
    the shared form renderer about plugin-specific field names.
    """

    key: str
    label: str
    unit: str
    default: Any = 0.0
    tab: str = ""
    widget: str = ""
    choices: Tuple[Any, ...] = ()

    def coerce(self, raw_value: Any, strict: bool = False) -> Any:
        """Coerce one raw value according to this field's declared type."""

        return coerce_field_value(self, raw_value, strict=strict)


ParseErrorHandler = Callable[[Field, Any, Any, Exception], None]


def coerce_field_value(
    field: Field,
    raw_value: Any,
    strict: bool = False,
) -> Any:
    """Convert one raw value using the historical OpenSpotter field rules.

    Non-strict conversion preserves the GUI behavior: unknown boolean strings
    become ``False`` and callers may replace conversion errors with defaults.
    Strict conversion additionally rejects ambiguous booleans, non-finite
    numbers, and fractional values for integer fields.
    """

    unit = str(field.unit).strip().lower()
    if unit == "bool" or isinstance(field.default, bool):
        if isinstance(raw_value, bool):
            return raw_value
        normalized = str(raw_value).strip().lower()
        if normalized in TRUE_VALUES:
            return True
        if strict:
            if normalized in FALSE_VALUES:
                return False
            raise ValueError("expected true or false")
        return False

    if unit == "int" or (
        isinstance(field.default, int) and not isinstance(field.default, bool)
    ):
        numeric = float(raw_value)
        if strict and (not math.isfinite(numeric) or not numeric.is_integer()):
            raise ValueError("expected a finite whole number")
        # Non-strict mode intentionally keeps the prior int(float(value))
        # behavior, including truncation of values such as "2.5".
        return int(numeric)

    if unit == "str" or isinstance(field.default, str):
        return str(raw_value)

    numeric = float(raw_value)
    if strict and not math.isfinite(numeric):
        raise ValueError("expected a finite number")
    return numeric


def parse_widget_entries(
    entries: Sequence[Any],
    fields: Sequence[Field],
    strict: bool = False,
    context: str = "Inputs",
    on_error: ParseErrorHandler = None,
) -> Dict[str, Any]:
    """Read ordered ``get()`` sources into a typed dictionary.

    In non-strict mode, invalid values use each field's default and optionally
    notify ``on_error``. Strict mode reports every invalid field together and
    rejects a widget list that is shorter than the schema.
    """

    if strict and len(entries) < len(fields):
        raise FieldInputError(
            "{} is missing {} required input field(s)".format(
                context,
                len(fields) - len(entries),
            )
        )

    result = {}
    errors = []
    for entry, field in zip(entries, fields):
        raw_value = "<unavailable>"
        try:
            raw_value = entry.get()
            value = coerce_field_value(field, raw_value, strict=strict)
        except Exception as exc:
            if strict:
                errors.append("{}: {}".format(field.label, exc))
                continue
            value = field.default
            if on_error is not None:
                on_error(field, raw_value, value, exc)
        result[field.key] = value

    if errors:
        raise FieldInputError(
            "{} contains invalid values:\n- {}".format(
                context,
                "\n- ".join(errors),
            )
        )
    return result


__all__ = [
    "FALSE_VALUES",
    "TRUE_VALUES",
    "Field",
    "FieldInputError",
    "ParseErrorHandler",
    "coerce_field_value",
    "parse_widget_entries",
]
