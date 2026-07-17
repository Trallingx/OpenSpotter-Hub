"""Typed workflow metadata contributed by core and pattern plugins.

The rendering engine consumes one deterministic aggregate. Contributions use
explicit order values so adding a plugin does not make output depend on module
discovery order.
"""

import copy
import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Sequence, Tuple

from .schema import Field


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TRIGGER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VARIABLE_PATH_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


class WorkflowContributionError(ValueError):
    """Raised when contributed workflow metadata is structurally invalid."""


class WorkflowContributionConflictError(WorkflowContributionError):
    """Raised when two contributors claim the same workflow contract item."""


@dataclass(frozen=True)
class FieldGroupContribution:
    """A named field namespace exposed to workflow expressions."""

    namespace: str
    fields: Sequence[Field]
    source: str
    order: int


@dataclass(frozen=True)
class TriggerContribution:
    """A named planner event that workflow sections may subscribe to."""

    name: str
    order: int


@dataclass(frozen=True)
class VariableScopeContribution:
    """Availability of one exact variable or namespace prefix.

    A trailing dot in ``pattern`` denotes a prefix. ``extend=True`` adds values
    to a base scope owned by another contribution; this lets pattern plugins
    extend shared runtime namespaces without redefining them.
    """

    pattern: str
    values: FrozenSet[str]
    order: int
    extend: bool = False


@dataclass(frozen=True)
class DerivedVariableContribution:
    """Metadata for a runtime value that is not backed by an input field."""

    name: str
    label: str
    value_type: str
    unit: str
    description: str
    order: int

    def compatibility_tuple(self) -> Tuple[str, str, str, str, str]:
        return (
            self.name,
            self.label,
            self.value_type,
            self.unit,
            self.description,
        )


@dataclass(frozen=True)
class ContextDefaultContribution:
    """A neutral preview value for one dotted workflow path."""

    path: str
    value: Any
    order: int


@dataclass(frozen=True)
class RequiredCustomVariableContribution:
    """A custom workflow variable required by a planner or plugin."""

    name: str
    order: int


@dataclass(frozen=True)
class WorkflowContribution:
    """One contributor's complete, immutable workflow metadata bundle."""

    contributor_id: str
    field_groups: Tuple[FieldGroupContribution, ...] = ()
    triggers: Tuple[TriggerContribution, ...] = ()
    variable_trigger_scopes: Tuple[VariableScopeContribution, ...] = ()
    variable_job_kind_scopes: Tuple[VariableScopeContribution, ...] = ()
    derived_variables: Tuple[DerivedVariableContribution, ...] = ()
    context_defaults: Tuple[ContextDefaultContribution, ...] = ()
    required_custom_variables: Tuple[RequiredCustomVariableContribution, ...] = ()


@dataclass(frozen=True)
class AggregatedWorkflowContributions:
    """Validated workflow metadata after deterministic conflict resolution."""

    field_groups: Tuple[FieldGroupContribution, ...]
    triggers: Tuple[str, ...]
    variable_trigger_scopes: Tuple[VariableScopeContribution, ...]
    variable_job_kind_scopes: Tuple[VariableScopeContribution, ...]
    derived_variables: Tuple[DerivedVariableContribution, ...]
    context_defaults: Mapping[str, Any]
    required_custom_variables: Tuple[str, ...]


def _validate_order(order: Any, description: str) -> None:
    if not isinstance(order, int) or isinstance(order, bool):
        raise WorkflowContributionError(
            "{} order must be an integer".format(description)
        )


def _ordered_records(
    contributions: Sequence[WorkflowContribution],
    attribute: str,
) -> list:
    records = []
    for contribution_index, contribution in enumerate(contributions):
        for record_index, record in enumerate(getattr(contribution, attribute)):
            _validate_order(
                getattr(record, "order", None),
                "{} from {!r}".format(attribute, contribution.contributor_id),
            )
            records.append(
                (
                    record.order,
                    contribution_index,
                    record_index,
                    contribution.contributor_id,
                    record,
                )
            )
    records.sort(key=lambda item: item[:3])
    return records


def _validate_contributions(
    contributions: Iterable[WorkflowContribution],
) -> Tuple[WorkflowContribution, ...]:
    detached = tuple(contributions)
    contributor_ids = set()
    for contribution in detached:
        if not isinstance(contribution, WorkflowContribution):
            raise WorkflowContributionError(
                "workflow contributions must be WorkflowContribution instances"
            )
        contributor_id = contribution.contributor_id
        if (
            not isinstance(contributor_id, str)
            or not contributor_id
            or contributor_id != contributor_id.strip()
        ):
            raise WorkflowContributionError(
                "workflow contributor_id must be a non-empty trimmed string"
            )
        if contributor_id in contributor_ids:
            raise WorkflowContributionConflictError(
                "duplicate workflow contributor_id {!r}".format(contributor_id)
            )
        contributor_ids.add(contributor_id)
    return detached


def _aggregate_field_groups(
    contributions: Sequence[WorkflowContribution],
) -> Tuple[FieldGroupContribution, ...]:
    groups = []
    namespace_owners = {}
    for _order, _contribution_index, _record_index, owner, group in _ordered_records(
        contributions,
        "field_groups",
    ):
        if not isinstance(group, FieldGroupContribution):
            raise WorkflowContributionError(
                "field_groups from {!r} contains an invalid record".format(owner)
            )
        if (
            not isinstance(group.namespace, str)
            or not _IDENTIFIER_RE.fullmatch(group.namespace)
        ):
            raise WorkflowContributionError(
                "invalid field-group namespace {!r} from {!r}".format(
                    group.namespace,
                    owner,
                )
            )
        previous_owner = namespace_owners.get(group.namespace)
        if previous_owner is not None:
            raise WorkflowContributionConflictError(
                "field-group namespace {!r} from {!r} conflicts with {!r}".format(
                    group.namespace,
                    owner,
                    previous_owner,
                )
            )
        if not isinstance(group.source, str) or not group.source.strip():
            raise WorkflowContributionError(
                "field group {!r} must have a non-empty source".format(
                    group.namespace
                )
            )
        if isinstance(group.fields, (str, bytes)) or not isinstance(
            group.fields,
            Sequence,
        ):
            raise WorkflowContributionError(
                "field group {!r} fields must be a sequence".format(
                    group.namespace
                )
            )
        field_keys = set()
        for field in group.fields:
            if not isinstance(field, Field):
                raise WorkflowContributionError(
                    "field group {!r} contains a non-Field value".format(
                        group.namespace
                    )
                )
            if (
                not isinstance(field.key, str)
                or not _IDENTIFIER_RE.fullmatch(field.key)
            ):
                raise WorkflowContributionError(
                    "field group {!r} contains invalid key {!r}".format(
                        group.namespace,
                        field.key,
                    )
                )
            if field.key in field_keys:
                raise WorkflowContributionConflictError(
                    "field group {!r} defines duplicate key {!r}".format(
                        group.namespace,
                        field.key,
                    )
                )
            field_keys.add(field.key)
        namespace_owners[group.namespace] = owner
        groups.append(group)
    return tuple(groups)


def _aggregate_triggers(
    contributions: Sequence[WorkflowContribution],
) -> Tuple[str, ...]:
    triggers = []
    owners = {}
    for _order, _contribution_index, _record_index, owner, trigger in _ordered_records(
        contributions,
        "triggers",
    ):
        if not isinstance(trigger, TriggerContribution):
            raise WorkflowContributionError(
                "triggers from {!r} contains an invalid record".format(owner)
            )
        if (
            not isinstance(trigger.name, str)
            or not _TRIGGER_RE.fullmatch(trigger.name)
        ):
            raise WorkflowContributionError(
                "invalid workflow trigger {!r} from {!r}".format(
                    trigger.name,
                    owner,
                )
            )
        previous_owner = owners.get(trigger.name)
        if previous_owner is not None:
            raise WorkflowContributionConflictError(
                "workflow trigger {!r} from {!r} conflicts with {!r}".format(
                    trigger.name,
                    owner,
                    previous_owner,
                )
            )
        owners[trigger.name] = owner
        triggers.append(trigger.name)
    return tuple(triggers)


def _validate_scope_pattern(pattern: Any, owner: str) -> None:
    if not isinstance(pattern, str) or not pattern:
        raise WorkflowContributionError(
            "variable scope from {!r} must have a non-empty pattern".format(owner)
        )
    candidate = pattern[:-1] if pattern.endswith(".") else pattern
    if not _VARIABLE_PATH_RE.fullmatch(candidate):
        raise WorkflowContributionError(
            "invalid variable scope pattern {!r} from {!r}".format(pattern, owner)
        )


def _aggregate_scopes(
    contributions: Sequence[WorkflowContribution],
    attribute: str,
    known_triggers: FrozenSet[str] = frozenset(),
) -> Tuple[VariableScopeContribution, ...]:
    scopes: Dict[str, Dict[str, Any]] = {}
    for sort_key in _ordered_records(contributions, attribute):
        _order, _contribution_index, _record_index, owner, scope = sort_key
        if not isinstance(scope, VariableScopeContribution):
            raise WorkflowContributionError(
                "{} from {!r} contains an invalid record".format(attribute, owner)
            )
        _validate_scope_pattern(scope.pattern, owner)
        if not isinstance(scope.values, frozenset):
            raise WorkflowContributionError(
                "scope {!r} values from {!r} must be a frozenset".format(
                    scope.pattern,
                    owner,
                )
            )
        if not isinstance(scope.extend, bool):
            raise WorkflowContributionError(
                "scope {!r} extend flag from {!r} must be Boolean".format(
                    scope.pattern,
                    owner,
                )
            )
        if any(not isinstance(value, str) or not value for value in scope.values):
            raise WorkflowContributionError(
                "scope {!r} from {!r} contains an invalid value".format(
                    scope.pattern,
                    owner,
                )
            )
        state = scopes.setdefault(
            scope.pattern,
            {
                "base": None,
                "base_owner": None,
                "extensions": [],
                "first_sort_key": sort_key[:3],
            },
        )
        if scope.extend:
            state["extensions"].append((owner, scope))
            continue
        if state["base"] is not None:
            raise WorkflowContributionConflictError(
                "variable scope {!r} from {!r} conflicts with {!r}".format(
                    scope.pattern,
                    owner,
                    state["base_owner"],
                )
            )
        state["base"] = scope
        state["base_owner"] = owner
        state["first_sort_key"] = sort_key[:3]

    aggregated = []
    for pattern, state in scopes.items():
        base = state["base"]
        if base is None:
            extension_owners = ", ".join(
                repr(owner) for owner, _scope in state["extensions"]
            )
            raise WorkflowContributionError(
                "variable scope {!r} is extended by {} but has no base owner".format(
                    pattern,
                    extension_owners,
                )
            )
        values = set(base.values)
        for _owner, extension in state["extensions"]:
            values.update(extension.values)
        if known_triggers:
            unknown_triggers = values - known_triggers
            if unknown_triggers:
                raise WorkflowContributionError(
                    "variable scope {!r} references unknown trigger(s): {}".format(
                        pattern,
                        ", ".join(sorted(unknown_triggers)),
                    )
                )
        aggregated.append(
            (
                state["first_sort_key"],
                VariableScopeContribution(
                    pattern=pattern,
                    values=frozenset(values),
                    order=base.order,
                ),
            )
        )
    aggregated.sort(key=lambda item: item[0])
    return tuple(scope for _sort_key, scope in aggregated)


def _aggregate_derived_variables(
    contributions: Sequence[WorkflowContribution],
    field_groups: Sequence[FieldGroupContribution],
) -> Tuple[DerivedVariableContribution, ...]:
    variable_owners = {
        "{}.{}".format(group.namespace, field.key): "field group {!r}".format(
            group.namespace
        )
        for group in field_groups
        for field in group.fields
    }
    derived_variables = []
    for _order, _contribution_index, _record_index, owner, variable in _ordered_records(
        contributions,
        "derived_variables",
    ):
        if not isinstance(variable, DerivedVariableContribution):
            raise WorkflowContributionError(
                "derived_variables from {!r} contains an invalid record".format(
                    owner
                )
            )
        if (
            not isinstance(variable.name, str)
            or not _VARIABLE_PATH_RE.fullmatch(variable.name)
        ):
            raise WorkflowContributionError(
                "invalid derived variable path {!r} from {!r}".format(
                    variable.name,
                    owner,
                )
            )
        previous_owner = variable_owners.get(variable.name)
        if previous_owner is not None:
            raise WorkflowContributionConflictError(
                "derived variable {!r} from {!r} conflicts with {}".format(
                    variable.name,
                    owner,
                    previous_owner,
                )
            )
        if variable.value_type not in ("number", "integer", "boolean", "string"):
            raise WorkflowContributionError(
                "derived variable {!r} has unsupported type {!r}".format(
                    variable.name,
                    variable.value_type,
                )
            )
        for label, value in (
            ("label", variable.label),
            ("unit", variable.unit),
            ("description", variable.description),
        ):
            if not isinstance(value, str):
                raise WorkflowContributionError(
                    "derived variable {!r} {} must be a string".format(
                        variable.name,
                        label,
                    )
                )
        variable_owners[variable.name] = repr(owner)
        derived_variables.append(variable)
    return tuple(derived_variables)


def _assign_context_default(
    context: Dict[str, Any],
    owners: Dict[str, str],
    path: str,
    value: Any,
    owner: str,
) -> None:
    if not isinstance(path, str) or not _VARIABLE_PATH_RE.fullmatch(path):
        raise WorkflowContributionError(
            "invalid context-default path {!r} from {!r}".format(path, owner)
        )
    previous_owner = owners.get(path)
    if previous_owner is not None:
        raise WorkflowContributionConflictError(
            "context default {!r} from {!r} conflicts with {!r}".format(
                path,
                owner,
                previous_owner,
            )
        )
    for existing_path, existing_owner in owners.items():
        if path.startswith(existing_path + ".") or existing_path.startswith(path + "."):
            raise WorkflowContributionConflictError(
                "context default {!r} from {!r} overlaps {!r} from {!r}".format(
                    path,
                    owner,
                    existing_path,
                    existing_owner,
                )
            )

    target = context
    parts = path.split(".")
    for part in parts[:-1]:
        current = target.get(part)
        if current is None:
            current = {}
            target[part] = current
        elif not isinstance(current, dict):
            raise WorkflowContributionConflictError(
                "context default {!r} from {!r} crosses a scalar value".format(
                    path,
                    owner,
                )
            )
        target = current
    target[parts[-1]] = copy.deepcopy(value)
    owners[path] = owner


def _aggregate_context_defaults(
    contributions: Sequence[WorkflowContribution],
    field_groups: Sequence[FieldGroupContribution],
) -> Mapping[str, Any]:
    context: Dict[str, Any] = {}
    owners: Dict[str, str] = {}
    for group in field_groups:
        context[group.namespace] = {}
        for field in group.fields:
            _assign_context_default(
                context,
                owners,
                "{}.{}".format(group.namespace, field.key),
                field.default,
                "field group {!r}".format(group.namespace),
            )

    for _order, _contribution_index, _record_index, owner, default in _ordered_records(
        contributions,
        "context_defaults",
    ):
        if not isinstance(default, ContextDefaultContribution):
            raise WorkflowContributionError(
                "context_defaults from {!r} contains an invalid record".format(owner)
            )
        _assign_context_default(
            context,
            owners,
            default.path,
            default.value,
            owner,
        )
    return context


def _aggregate_required_custom_variables(
    contributions: Sequence[WorkflowContribution],
) -> Tuple[str, ...]:
    required = []
    owners = {}
    for _order, _contribution_index, _record_index, owner, variable in _ordered_records(
        contributions,
        "required_custom_variables",
    ):
        if not isinstance(variable, RequiredCustomVariableContribution):
            raise WorkflowContributionError(
                "required_custom_variables from {!r} contains an invalid record".format(
                    owner
                )
            )
        if (
            not isinstance(variable.name, str)
            or not _IDENTIFIER_RE.fullmatch(variable.name)
        ):
            raise WorkflowContributionError(
                "invalid required custom variable {!r} from {!r}".format(
                    variable.name,
                    owner,
                )
            )
        previous_owner = owners.get(variable.name)
        if previous_owner is not None:
            raise WorkflowContributionConflictError(
                "required custom variable {!r} from {!r} conflicts with {!r}".format(
                    variable.name,
                    owner,
                    previous_owner,
                )
            )
        owners[variable.name] = owner
        required.append(variable.name)
    return tuple(required)


def aggregate_workflow_contributions(
    contributions: Iterable[WorkflowContribution],
) -> AggregatedWorkflowContributions:
    """Validate and deterministically combine workflow metadata."""

    contribution_records = _validate_contributions(contributions)
    field_groups = _aggregate_field_groups(contribution_records)
    triggers = _aggregate_triggers(contribution_records)
    trigger_scopes = _aggregate_scopes(
        contribution_records,
        "variable_trigger_scopes",
        frozenset(triggers),
    )
    job_kind_scopes = _aggregate_scopes(
        contribution_records,
        "variable_job_kind_scopes",
    )
    derived_variables = _aggregate_derived_variables(
        contribution_records,
        field_groups,
    )
    context_defaults = _aggregate_context_defaults(
        contribution_records,
        field_groups,
    )
    required_custom_variables = _aggregate_required_custom_variables(
        contribution_records
    )
    return AggregatedWorkflowContributions(
        field_groups=field_groups,
        triggers=triggers,
        variable_trigger_scopes=trigger_scopes,
        variable_job_kind_scopes=job_kind_scopes,
        derived_variables=derived_variables,
        context_defaults=context_defaults,
        required_custom_variables=required_custom_variables,
    )


def aggregate_registry_workflow_contributions(
    registry: Any,
    core_contribution: WorkflowContribution,
) -> AggregatedWorkflowContributions:
    """Aggregate core metadata and optional contributions from registry plugins."""

    contributions = [core_contribution]
    for plugin_id, plugin in registry.items():
        contribution = getattr(plugin, "workflow_contribution", None)
        if contribution is None:
            continue
        if not isinstance(contribution, WorkflowContribution):
            raise WorkflowContributionError(
                "plugin {!r} workflow_contribution has an invalid type".format(
                    plugin_id
                )
            )
        if contribution.contributor_id != plugin_id:
            raise WorkflowContributionConflictError(
                "plugin {!r} exposes workflow contribution {!r}".format(
                    plugin_id,
                    contribution.contributor_id,
                )
            )
        contributions.append(contribution)
    return aggregate_workflow_contributions(contributions)


CORE_TRIGGERS = (
    TriggerContribution("job_start", 0),
    TriggerContribution("syringe_reload", 1),
    TriggerContribution("syringe_empty_start", 16),
    TriggerContribution("rinse_cycle", 17),
    TriggerContribution("rinse_midpoint", 18),
    TriggerContribution("syringe_empty_end", 19),
    TriggerContribution("job_end", 20),
)

CORE_VARIABLE_TRIGGER_SCOPES = (
    VariableScopeContribution(
        "container.",
        frozenset(
            (
                "syringe_reload",
                "syringe_empty_start",
                "rinse_cycle",
                "rinse_midpoint",
                "syringe_empty_end",
            )
        ),
        1,
    ),
    VariableScopeContribution("runtime.spot.", frozenset(), 11),
    VariableScopeContribution(
        "runtime.refill.",
        frozenset(("syringe_reload",)),
        12,
    ),
    VariableScopeContribution(
        "runtime.rinse.",
        frozenset(
            (
                "syringe_empty_start",
                "rinse_cycle",
                "rinse_midpoint",
                "syringe_empty_end",
            )
        ),
        14,
    ),
)

CORE_VARIABLE_JOB_KIND_SCOPES = (
    VariableScopeContribution("runtime.spot.", frozenset(), 13),
)

CORE_DERIVED_VARIABLES = (
    DerivedVariableContribution(
        "acceptance.x_left",
        "Acceptance left",
        "number",
        "mm",
        "Computed acceptance-square left edge",
        0,
    ),
    DerivedVariableContribution(
        "acceptance.x_right",
        "Acceptance right",
        "number",
        "mm",
        "Computed acceptance-square right edge",
        1,
    ),
    DerivedVariableContribution(
        "acceptance.y_bottom",
        "Acceptance bottom",
        "number",
        "mm",
        "Computed acceptance-square bottom edge",
        2,
    ),
    DerivedVariableContribution(
        "acceptance.y_top",
        "Acceptance top",
        "number",
        "mm",
        "Computed acceptance-square top edge",
        3,
    ),
    DerivedVariableContribution(
        "container.id",
        "Container number",
        "integer",
        "",
        "Active loading or emptying container",
        4,
    ),
    DerivedVariableContribution(
        "container.x",
        "Container X",
        "number",
        "mm",
        "Active container X coordinate",
        5,
    ),
    DerivedVariableContribution(
        "container.y",
        "Container Y",
        "number",
        "mm",
        "Active container Y coordinate",
        6,
    ),
    DerivedVariableContribution(
        "container.z",
        "Container fill Z",
        "number",
        "mm",
        "Active container fill height",
        7,
    ),
    DerivedVariableContribution(
        "runtime.job.kind",
        "Job kind",
        "string",
        "",
        "Grid, spiral, or preview job",
        13,
    ),
    DerivedVariableContribution(
        "runtime.job.pattern_index",
        "Pattern index",
        "integer",
        "",
        "One-based active pattern index",
        14,
    ),
    DerivedVariableContribution(
        "runtime.spot.index",
        "Spot index",
        "integer",
        "",
        "Zero-based spot index",
        15,
    ),
    DerivedVariableContribution(
        "runtime.spot.x",
        "Spot X",
        "number",
        "mm",
        "Planned spot X coordinate",
        19,
    ),
    DerivedVariableContribution(
        "runtime.spot.y",
        "Spot Y",
        "number",
        "mm",
        "Planned spot Y coordinate",
        20,
    ),
    DerivedVariableContribution(
        "runtime.spot.dispense_mm",
        "Spot dispense",
        "number",
        "mm",
        "Plunger travel for this spot",
        21,
    ),
    DerivedVariableContribution(
        "runtime.refill.reason",
        "Refill reason",
        "string",
        "",
        "Why a refill was planned",
        28,
    ),
    DerivedVariableContribution(
        "runtime.refill.dynamic",
        "Dynamic refill",
        "boolean",
        "",
        "Whether to include dynamic refill diagnostics",
        29,
    ),
    DerivedVariableContribution(
        "runtime.refill.container_id",
        "Refill container",
        "integer",
        "",
        "Selected loading container number",
        30,
    ),
    DerivedVariableContribution(
        "runtime.refill.fill_mm",
        "Aspirated travel",
        "number",
        "mm",
        "Fill plus priming plunger travel",
        31,
    ),
    DerivedVariableContribution(
        "runtime.refill.priming_mm",
        "Priming travel",
        "number",
        "mm",
        "Priming plunger travel",
        32,
    ),
    DerivedVariableContribution(
        "runtime.refill.target_fill_mm",
        "Target fill",
        "number",
        "mm",
        "Useful target plunger travel",
        33,
    ),
    DerivedVariableContribution(
        "runtime.refill.target_fill_ul",
        "Target fill",
        "number",
        "uL",
        "Useful target volume",
        34,
    ),
    DerivedVariableContribution(
        "runtime.refill.remaining_spots_mm",
        "Remaining spots",
        "number",
        "mm",
        "Remaining grid plunger demand",
        35,
    ),
    DerivedVariableContribution(
        "runtime.refill.cleaning_mm",
        "Cleaning demand",
        "number",
        "mm",
        "Reserved cleaning demand",
        36,
    ),
    DerivedVariableContribution(
        "runtime.refill.reserve_mm",
        "Reserve",
        "number",
        "mm",
        "Reserved plunger travel",
        37,
    ),
    DerivedVariableContribution(
        "runtime.refill.total_needed_mm",
        "Total required",
        "number",
        "mm",
        "Total calculated plunger demand",
        38,
    ),
    DerivedVariableContribution(
        "runtime.refill.cap_mm",
        "Refill cap",
        "number",
        "mm",
        "Maximum permitted refill",
        39,
    ),
    DerivedVariableContribution(
        "runtime.rinse.cycle",
        "Rinse cycle",
        "integer",
        "",
        "Rinse cycle number, zero when disabled",
        43,
    ),
    DerivedVariableContribution(
        "runtime.rinse.phase",
        "Rinse phase",
        "integer",
        "",
        "First or second rinse pass",
        44,
    ),
    DerivedVariableContribution(
        "runtime.rinse.max_mm",
        "Rinse aspiration",
        "number",
        "mm",
        "Rinse aspiration endpoint",
        45,
    ),
    DerivedVariableContribution(
        "runtime.rinse.min_mm",
        "Rinse dispense",
        "number",
        "mm",
        "Rinse dispense endpoint",
        46,
    ),
)

CORE_CONTEXT_DEFAULTS = (
    ContextDefaultContribution("acceptance.x_left", 0.0, 100),
    ContextDefaultContribution("acceptance.x_right", 0.0, 101),
    ContextDefaultContribution("acceptance.y_bottom", 0.0, 102),
    ContextDefaultContribution("acceptance.y_top", 0.0, 103),
    ContextDefaultContribution("container.id", 0, 110),
    ContextDefaultContribution("container.x", 0.0, 111),
    ContextDefaultContribution("container.y", 0.0, 112),
    ContextDefaultContribution("container.z", 0.0, 113),
    ContextDefaultContribution("runtime.job.kind", "preview", 120),
    ContextDefaultContribution("runtime.job.pattern_index", 0, 121),
    ContextDefaultContribution("runtime.spot.index", 0, 130),
    ContextDefaultContribution("runtime.spot.x", 0.0, 134),
    ContextDefaultContribution("runtime.spot.y", 0.0, 135),
    ContextDefaultContribution("runtime.spot.dispense_mm", 0.0, 136),
    ContextDefaultContribution("runtime.refill.reason", "preview", 150),
    ContextDefaultContribution("runtime.refill.dynamic", False, 151),
    ContextDefaultContribution("runtime.refill.container_id", 0, 152),
    ContextDefaultContribution("runtime.refill.fill_mm", 0.0, 153),
    ContextDefaultContribution("runtime.refill.priming_mm", 0.0, 154),
    ContextDefaultContribution("runtime.refill.target_fill_mm", 0.0, 155),
    ContextDefaultContribution("runtime.refill.target_fill_ul", 0.0, 156),
    ContextDefaultContribution("runtime.refill.remaining_spots_mm", 0.0, 157),
    ContextDefaultContribution("runtime.refill.cleaning_mm", 0.0, 158),
    ContextDefaultContribution("runtime.refill.reserve_mm", 0.0, 159),
    ContextDefaultContribution("runtime.refill.total_needed_mm", 0.0, 160),
    ContextDefaultContribution("runtime.refill.cap_mm", 0.0, 161),
    ContextDefaultContribution("runtime.rinse.cycle", 0, 180),
    ContextDefaultContribution("runtime.rinse.phase", 0, 181),
    ContextDefaultContribution("runtime.rinse.max_mm", 0.0, 182),
    ContextDefaultContribution("runtime.rinse.min_mm", 0.0, 183),
)

CORE_REQUIRED_CUSTOM_VARIABLES = (
    RequiredCustomVariableContribution("syringe_mm_per_ul", 0),
)


def build_core_workflow_contribution(
    global_fields: Sequence[Field],
) -> WorkflowContribution:
    """Bind the application-wide field schema to core-owned workflow metadata."""

    return WorkflowContribution(
        contributor_id="core",
        field_groups=(
            FieldGroupContribution(
                namespace="global",
                fields=global_fields,
                source="GLOBAL_FIELDS",
                order=0,
            ),
        ),
        triggers=CORE_TRIGGERS,
        variable_trigger_scopes=CORE_VARIABLE_TRIGGER_SCOPES,
        variable_job_kind_scopes=CORE_VARIABLE_JOB_KIND_SCOPES,
        derived_variables=CORE_DERIVED_VARIABLES,
        context_defaults=CORE_CONTEXT_DEFAULTS,
        required_custom_variables=CORE_REQUIRED_CUSTOM_VARIABLES,
    )


__all__ = [
    "AggregatedWorkflowContributions",
    "ContextDefaultContribution",
    "DerivedVariableContribution",
    "FieldGroupContribution",
    "RequiredCustomVariableContribution",
    "TriggerContribution",
    "VariableScopeContribution",
    "WorkflowContribution",
    "WorkflowContributionConflictError",
    "WorkflowContributionError",
    "aggregate_registry_workflow_contributions",
    "aggregate_workflow_contributions",
    "build_core_workflow_contribution",
]
