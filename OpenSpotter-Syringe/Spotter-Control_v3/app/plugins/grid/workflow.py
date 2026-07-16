"""Workflow metadata owned by the built-in grid plugin."""

from ...core.workflow import (
    ContextDefaultContribution,
    DerivedVariableContribution,
    FieldGroupContribution,
    TriggerContribution,
    VariableScopeContribution,
    WorkflowContribution,
)
from .fields import CLEANING_FIELDS, GRID_FIELDS, WASHING_FIELDS


_grid_spot_triggers = frozenset(
    (
        "grid_spot_move",
        "grid_row_start",
        "grid_spot_dispense",
        "cleaning_spot_move",
        "cleaning_row_start",
        "cleaning_spot_dispense",
    )
)

_cleaning_triggers = frozenset(
    (
        "cleaning_start",
        "cleaning_spot_move",
        "cleaning_row_start",
        "cleaning_spot_dispense",
    )
)

_washing_triggers = frozenset(
    (
        "washing_start",
        "washing_cycle",
        "washing_end",
    )
)


WORKFLOW_CONTRIBUTION = WorkflowContribution(
    contributor_id="grid",
    field_groups=(
        FieldGroupContribution(
            "grid",
            GRID_FIELDS,
            "GRID_FIELDS",
            1,
        ),
        FieldGroupContribution(
            "cleaning",
            CLEANING_FIELDS,
            "CLEANING_FIELDS",
            2,
        ),
        FieldGroupContribution(
            "washing",
            WASHING_FIELDS,
            "WASHING_FIELDS",
            3,
        ),
    ),
    triggers=(
        TriggerContribution("grid_start", 2),
        TriggerContribution("grid_spot_move", 3),
        TriggerContribution("grid_row_start", 4),
        TriggerContribution("grid_spot_dispense", 5),
        TriggerContribution("cleaning_start", 9),
        TriggerContribution("cleaning_spot_move", 10),
        TriggerContribution("cleaning_row_start", 11),
        TriggerContribution("cleaning_spot_dispense", 12),
        TriggerContribution("washing_start", 13),
        TriggerContribution("washing_cycle", 14),
        TriggerContribution("washing_end", 15),
    ),
    variable_trigger_scopes=(
        VariableScopeContribution(
            "cleaning.cycle",
            _cleaning_triggers,
            0,
        ),
        VariableScopeContribution(
            "runtime.spot.row",
            _grid_spot_triggers,
            8,
        ),
        VariableScopeContribution(
            "runtime.spot.column",
            _grid_spot_triggers,
            9,
        ),
        VariableScopeContribution(
            "runtime.spot.is_row_start",
            _grid_spot_triggers,
            10,
        ),
        VariableScopeContribution(
            "runtime.spot.",
            _grid_spot_triggers,
            11,
            extend=True,
        ),
        VariableScopeContribution(
            "runtime.washing.",
            _washing_triggers,
            13,
        ),
    ),
    variable_job_kind_scopes=(
        VariableScopeContribution("grid.", frozenset(("grid",)), 0),
        VariableScopeContribution("cleaning.", frozenset(("grid",)), 1),
        VariableScopeContribution("washing.", frozenset(("grid",)), 2),
        VariableScopeContribution(
            "runtime.spot.row",
            frozenset(("grid",)),
            10,
        ),
        VariableScopeContribution(
            "runtime.spot.column",
            frozenset(("grid",)),
            11,
        ),
        VariableScopeContribution(
            "runtime.spot.is_row_start",
            frozenset(("grid",)),
            12,
        ),
        VariableScopeContribution(
            "runtime.spot.",
            frozenset(("grid",)),
            13,
            extend=True,
        ),
        VariableScopeContribution(
            "runtime.washing.",
            frozenset(("grid",)),
            14,
        ),
    ),
    derived_variables=(
        DerivedVariableContribution(
            "grid.name",
            "Grid name",
            "string",
            "",
            "Current grid display name",
            8,
        ),
        DerivedVariableContribution(
            "grid.color",
            "Grid color",
            "string",
            "",
            "Current grid display color",
            9,
        ),
        DerivedVariableContribution(
            "cleaning.cycle",
            "Cleaning cycle",
            "integer",
            "",
            "Zero-based cleaning-grid cycle",
            10,
        ),
        DerivedVariableContribution(
            "runtime.spot.row",
            "Spot row",
            "integer",
            "",
            "Zero-based row index",
            17,
        ),
        DerivedVariableContribution(
            "runtime.spot.column",
            "Spot column",
            "integer",
            "",
            "Zero-based column index",
            18,
        ),
        DerivedVariableContribution(
            "runtime.spot.is_row_start",
            "Row start",
            "boolean",
            "",
            "Whether this spot starts a row",
            27,
        ),
        DerivedVariableContribution(
            "runtime.washing.cycle",
            "Wash cycle",
            "integer",
            "",
            "Zero-based washing cycle",
            40,
        ),
        DerivedVariableContribution(
            "runtime.washing.x_start",
            "Wash X start",
            "number",
            "mm",
            "Washing stroke start",
            41,
        ),
        DerivedVariableContribution(
            "runtime.washing.x_end",
            "Wash X end",
            "number",
            "mm",
            "Washing stroke end",
            42,
        ),
    ),
    context_defaults=(
        ContextDefaultContribution("grid.name", "Grid", 0),
        ContextDefaultContribution("grid.color", "green", 1),
        ContextDefaultContribution("cleaning.cycle", 0, 2),
        ContextDefaultContribution("runtime.spot.row", 0, 132),
        ContextDefaultContribution("runtime.spot.column", 0, 133),
        ContextDefaultContribution(
            "runtime.spot.is_row_start",
            True,
            142,
        ),
        ContextDefaultContribution("runtime.washing.cycle", 0, 170),
        ContextDefaultContribution("runtime.washing.x_start", 0.0, 171),
        ContextDefaultContribution("runtime.washing.x_end", 0.0, 172),
    ),
)


__all__ = ["WORKFLOW_CONTRIBUTION"]
