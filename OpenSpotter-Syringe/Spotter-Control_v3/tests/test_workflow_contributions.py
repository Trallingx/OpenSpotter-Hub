import unittest

from app import gcode_workflow
from app.core.plugins import PluginManifest, PluginRegistry
from app.core.workflow import (
    ContextDefaultContribution,
    TriggerContribution,
    VariableScopeContribution,
    WorkflowContribution,
    WorkflowContributionConflictError,
    WorkflowContributionError,
    aggregate_registry_workflow_contributions,
    aggregate_workflow_contributions,
    build_core_workflow_contribution,
)
from app.input_configs import (
    CLEANING_FIELDS,
    GLOBAL_FIELDS,
    GRID_FIELDS,
    SPIRAL_FIELDS,
    WASHING_FIELDS,
)


EXPECTED_TRIGGERS = (
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


class ContributingPlugin:
    manifest = PluginManifest(
        id="contributor",
        display_name="Contributor",
        version="1.0.0",
    )
    name = manifest.id
    workflow_contribution = WorkflowContribution(
        contributor_id="different-id",
    )

    def plan(self, context):
        return []


class WorkflowContributionTests(unittest.TestCase):
    def test_builtin_registry_aggregate_preserves_compatibility_order(self):
        registry = PluginRegistry()
        registry.discover_builtins("app.plugins")

        aggregate = aggregate_registry_workflow_contributions(
            registry,
            build_core_workflow_contribution(GLOBAL_FIELDS),
        )

        self.assertEqual(registry.ids(), ("grid", "spiral"))
        self.assertEqual(aggregate.triggers, EXPECTED_TRIGGERS)
        self.assertEqual(gcode_workflow.EVENT_TRIGGERS, EXPECTED_TRIGGERS)
        self.assertEqual(
            [group.namespace for group in aggregate.field_groups],
            ["global", "grid", "cleaning", "washing", "spiral"],
        )
        self.assertEqual(
            [group.fields for group in aggregate.field_groups],
            [
                GLOBAL_FIELDS,
                GRID_FIELDS,
                CLEANING_FIELDS,
                WASHING_FIELDS,
                SPIRAL_FIELDS,
            ],
        )
        for (_namespace, compatibility_fields, _source), expected_fields in zip(
            gcode_workflow._FIELD_GROUPS,
            (
                GLOBAL_FIELDS,
                GRID_FIELDS,
                CLEANING_FIELDS,
                WASHING_FIELDS,
                SPIRAL_FIELDS,
            ),
        ):
            self.assertIs(compatibility_fields, expected_fields)
        self.assertEqual(
            [scope.pattern for scope in aggregate.variable_trigger_scopes],
            [
                "cleaning.cycle",
                "container.",
                "runtime.spot.start_index",
                "runtime.spot.dispense_ul",
                "runtime.spot.segment_length",
                "runtime.spot.theta",
                "runtime.spot.radius",
                "runtime.spot.continuous",
                "runtime.spot.row",
                "runtime.spot.column",
                "runtime.spot.is_row_start",
                "runtime.spot.",
                "runtime.refill.",
                "runtime.washing.",
                "runtime.rinse.",
            ],
        )
        shared_spot_scope = next(
            scope
            for scope in aggregate.variable_trigger_scopes
            if scope.pattern == "runtime.spot."
        )
        self.assertEqual(
            shared_spot_scope.values,
            frozenset(
                (
                    "grid_spot_move",
                    "grid_row_start",
                    "grid_spot_dispense",
                    "cleaning_spot_move",
                    "cleaning_row_start",
                    "cleaning_spot_dispense",
                    "spiral_drop",
                    "spiral_continuous",
                )
            ),
        )
        self.assertEqual(
            aggregate.required_custom_variables,
            ("syringe_mm_per_ul", "spiral_resolution_radians"),
        )
        self.assertEqual(
            list(aggregate.context_defaults),
            [
                "global",
                "grid",
                "cleaning",
                "washing",
                "spiral",
                "acceptance",
                "container",
                "runtime",
            ],
        )
        self.assertEqual(
            list(aggregate.context_defaults["runtime"]["spot"]),
            [
                "index",
                "start_index",
                "row",
                "column",
                "x",
                "y",
                "dispense_mm",
                "dispense_ul",
                "segment_length",
                "theta",
                "radius",
                "continuous",
                "is_row_start",
            ],
        )
        self.assertEqual(
            gcode_workflow.build_runtime_context_defaults(),
            aggregate.context_defaults,
        )

    def test_scope_extensions_merge_without_redefining_the_base(self):
        core = WorkflowContribution(
            contributor_id="core",
            triggers=(
                TriggerContribution("first_event", 0),
                TriggerContribution("second_event", 1),
            ),
            variable_trigger_scopes=(
                VariableScopeContribution(
                    "runtime.point.",
                    frozenset(("first_event",)),
                    0,
                ),
            ),
        )
        plugin = WorkflowContribution(
            contributor_id="plugin",
            variable_trigger_scopes=(
                VariableScopeContribution(
                    "runtime.point.",
                    frozenset(("second_event",)),
                    0,
                    extend=True,
                ),
            ),
        )

        aggregate = aggregate_workflow_contributions((plugin, core))

        self.assertEqual(aggregate.triggers, ("first_event", "second_event"))
        self.assertEqual(
            aggregate.variable_trigger_scopes[0].values,
            frozenset(("first_event", "second_event")),
        )

    def test_duplicate_contract_items_report_their_owners(self):
        with self.subTest("trigger"):
            first = WorkflowContribution(
                contributor_id="first",
                triggers=(TriggerContribution("same_event", 0),),
            )
            second = WorkflowContribution(
                contributor_id="second",
                triggers=(TriggerContribution("same_event", 1),),
            )
            with self.assertRaisesRegex(
                WorkflowContributionConflictError,
                "same_event.*second.*first",
            ):
                aggregate_workflow_contributions((first, second))

        with self.subTest("context default"):
            first = WorkflowContribution(
                contributor_id="first",
                context_defaults=(
                    ContextDefaultContribution("runtime.value", 1, 0),
                ),
            )
            second = WorkflowContribution(
                contributor_id="second",
                context_defaults=(
                    ContextDefaultContribution("runtime.value", 2, 1),
                ),
            )
            with self.assertRaisesRegex(
                WorkflowContributionConflictError,
                "runtime.value.*second.*first",
            ):
                aggregate_workflow_contributions((first, second))

        with self.subTest("scope owner"):
            first = WorkflowContribution(
                contributor_id="first",
                variable_job_kind_scopes=(
                    VariableScopeContribution(
                        "pattern.",
                        frozenset(("first",)),
                        0,
                    ),
                ),
            )
            second = WorkflowContribution(
                contributor_id="second",
                variable_job_kind_scopes=(
                    VariableScopeContribution(
                        "pattern.",
                        frozenset(("second",)),
                        1,
                    ),
                ),
            )
            with self.assertRaisesRegex(
                WorkflowContributionConflictError,
                "pattern.*second.*first",
            ):
                aggregate_workflow_contributions((first, second))

    def test_scope_extension_requires_a_base_owner(self):
        contribution = WorkflowContribution(
            contributor_id="orphan",
            variable_job_kind_scopes=(
                VariableScopeContribution(
                    "orphan.",
                    frozenset(("orphan",)),
                    0,
                    extend=True,
                ),
            ),
        )

        with self.assertRaisesRegex(
            WorkflowContributionError,
            "no base owner",
        ):
            aggregate_workflow_contributions((contribution,))

    def test_registry_rejects_contribution_id_that_differs_from_plugin_id(self):
        registry = PluginRegistry()
        registry.register(ContributingPlugin())

        with self.assertRaisesRegex(
            WorkflowContributionConflictError,
            "contributor.*different-id",
        ):
            aggregate_registry_workflow_contributions(
                registry,
                WorkflowContribution(contributor_id="core"),
            )


if __name__ == "__main__":
    unittest.main()
