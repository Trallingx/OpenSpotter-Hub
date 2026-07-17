"""Workflow metadata owned by the built-in spiral plugin."""

from ...core.workflow import (
    ContextDefaultContribution,
    DerivedVariableContribution,
    FieldGroupContribution,
    RequiredCustomVariableContribution,
    TriggerContribution,
    VariableScopeContribution,
    WorkflowContribution,
)
from .fields import SPIRAL_FIELDS


_spiral_spot_triggers = frozenset(("spiral_drop", "spiral_continuous"))


WORKFLOW_CONTRIBUTION = WorkflowContribution(
    contributor_id="spiral",
    field_groups=(
        FieldGroupContribution(
            "spiral",
            SPIRAL_FIELDS,
            "SPIRAL_FIELDS",
            4,
        ),
    ),
    triggers=(
        TriggerContribution("spiral_start", 6),
        TriggerContribution("spiral_drop", 7),
        TriggerContribution("spiral_continuous", 8),
    ),
    variable_trigger_scopes=(
        VariableScopeContribution(
            "runtime.spot.start_index",
            _spiral_spot_triggers,
            2,
        ),
        VariableScopeContribution(
            "runtime.spot.dispense_ul",
            _spiral_spot_triggers,
            3,
        ),
        VariableScopeContribution(
            "runtime.spot.segment_length",
            _spiral_spot_triggers,
            4,
        ),
        VariableScopeContribution(
            "runtime.spot.theta",
            _spiral_spot_triggers,
            5,
        ),
        VariableScopeContribution(
            "runtime.spot.radius",
            _spiral_spot_triggers,
            6,
        ),
        VariableScopeContribution(
            "runtime.spot.continuous",
            _spiral_spot_triggers,
            7,
        ),
        VariableScopeContribution(
            "runtime.spot.",
            _spiral_spot_triggers,
            11,
            extend=True,
        ),
    ),
    variable_job_kind_scopes=(
        VariableScopeContribution("spiral.", frozenset(("spiral",)), 3),
        VariableScopeContribution(
            "runtime.spot.start_index",
            frozenset(("spiral",)),
            4,
        ),
        VariableScopeContribution(
            "runtime.spot.dispense_ul",
            frozenset(("spiral",)),
            5,
        ),
        VariableScopeContribution(
            "runtime.spot.segment_length",
            frozenset(("spiral",)),
            6,
        ),
        VariableScopeContribution(
            "runtime.spot.theta",
            frozenset(("spiral",)),
            7,
        ),
        VariableScopeContribution(
            "runtime.spot.radius",
            frozenset(("spiral",)),
            8,
        ),
        VariableScopeContribution(
            "runtime.spot.continuous",
            frozenset(("spiral",)),
            9,
        ),
        VariableScopeContribution(
            "runtime.spot.",
            frozenset(("spiral",)),
            13,
            extend=True,
        ),
    ),
    derived_variables=(
        DerivedVariableContribution(
            "spiral.name",
            "Spiral name",
            "string",
            "",
            "Current spiral display name",
            11,
        ),
        DerivedVariableContribution(
            "spiral.color",
            "Spiral color",
            "string",
            "",
            "Current spiral display color",
            12,
        ),
        DerivedVariableContribution(
            "runtime.spot.start_index",
            "Spiral start",
            "integer",
            "",
            "Zero-based multi-start spiral index",
            16,
        ),
        DerivedVariableContribution(
            "runtime.spot.dispense_ul",
            "Spot volume",
            "number",
            "uL",
            "Liquid volume for the current spiral point",
            22,
        ),
        DerivedVariableContribution(
            "runtime.spot.segment_length",
            "Segment length",
            "number",
            "mm",
            "Current spiral segment length",
            23,
        ),
        DerivedVariableContribution(
            "runtime.spot.theta",
            "Spiral angle",
            "number",
            "rad",
            "Current spiral angular position",
            24,
        ),
        DerivedVariableContribution(
            "runtime.spot.radius",
            "Spiral radius",
            "number",
            "mm",
            "Current spiral radius",
            25,
        ),
        DerivedVariableContribution(
            "runtime.spot.continuous",
            "Continuous segment",
            "boolean",
            "",
            "Whether the current spiral point is a continuous segment",
            26,
        ),
    ),
    context_defaults=(
        ContextDefaultContribution("spiral.name", "Spiral", 3),
        ContextDefaultContribution("spiral.color", "orange", 4),
        ContextDefaultContribution("runtime.spot.start_index", 0, 131),
        ContextDefaultContribution("runtime.spot.dispense_ul", 0.0, 137),
        ContextDefaultContribution("runtime.spot.segment_length", 0.0, 138),
        ContextDefaultContribution("runtime.spot.theta", 0.0, 139),
        ContextDefaultContribution("runtime.spot.radius", 0.0, 140),
        ContextDefaultContribution("runtime.spot.continuous", False, 141),
    ),
    required_custom_variables=(
        RequiredCustomVariableContribution(
            "spiral_resolution_radians",
            1,
        ),
    ),
)


__all__ = ["WORKFLOW_CONTRIBUTION"]
