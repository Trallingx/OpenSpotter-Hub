import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import gcode_workflow as workflow_module
from app.gcode_workflow import (
    EVENT_TRIGGERS,
    WorkflowEngine,
    WorkflowStore,
    WorkflowValidationError,
    build_runtime_context_defaults,
    build_variable_catalog,
    default_workflow,
    render_template,
    render_preview,
    validate_workflow,
)
from app.paths import RESOURCE_CONFIG_DIR, WORKFLOW_CONFIG


PROJECT_DIR = Path(__file__).resolve().parents[1]


def minimal_workflow(custom_variables=None, condition="", template=""):
    supplied = list(custom_variables or [])
    supplied_names = {variable.get("name") for variable in supplied}
    required = [
        custom_variable("syringe_mm_per_ul", value=1.0),
        custom_variable("spiral_resolution_radians", value=0.1),
    ]
    return {
        "schema_version": 1,
        "name": "Workflow Test",
        "custom_variables": [
            *supplied,
            *(variable for variable in required if variable["name"] not in supplied_names),
        ],
        "blocks": [
            {
                "id": "test-block",
                "name": "Test Block",
                "role": "start",
                "enabled": True,
                "sections": [
                    {
                        "id": "test-section",
                        "name": "Test Section",
                        "trigger": "job_start",
                        "condition": condition,
                        "template": template,
                    }
                ],
            }
        ],
    }


def custom_variable(name, *, value=None, expression=None, variable_type="number"):
    variable = {
        "name": name,
        "label": name.replace("_", " ").title(),
        "type": variable_type,
        "unit": "",
        "description": f"Test variable {name}",
    }
    if expression is not None:
        variable["expression"] = expression
    else:
        variable["value"] = value
    return variable


class DefaultWorkflowTests(unittest.TestCase):
    def test_packaged_template_and_writable_runtime_paths_are_distinct(self):
        self.assertEqual(
            workflow_module.SHIPPED_WORKFLOW_PATH,
            RESOURCE_CONFIG_DIR / "config_gcode_workflow.json",
        )
        self.assertEqual(workflow_module.DEFAULT_WORKFLOW_PATH, WORKFLOW_CONFIG)
        self.assertEqual(WorkflowStore().path, WORKFLOW_CONFIG)

        with mock.patch.object(
            workflow_module,
            "load_workflow",
            return_value={"source": "packaged"},
        ) as load_workflow:
            self.assertEqual(
                workflow_module.default_workflow(),
                {"source": "packaged"},
            )
        load_workflow.assert_called_once_with(
            workflow_module.SHIPPED_WORKFLOW_PATH
        )

    def test_default_workflow_validates_and_exposes_five_ordered_blocks(self):
        workflow = validate_workflow(default_workflow())

        self.assertEqual(
            [block["role"] for block in workflow["blocks"]],
            ["start", "loading", "printing", "cleaning", "end"],
        )
        triggers = {
            section["trigger"]
            for block in workflow["blocks"]
            for section in block["sections"]
        }
        self.assertTrue(
            {
                "job_start",
                "syringe_reload",
                "grid_start",
                "grid_spot_move",
                "grid_spot_dispense",
                "cleaning_start",
                "job_end",
            }.issubset(triggers)
        )
        custom_names = {variable["name"] for variable in workflow["custom_variables"]}
        self.assertIn("syringe_mm_per_ul", custom_names)
        self.assertIn("spiral_resolution_radians", custom_names)

    def test_all_shipped_events_render_with_complete_preview_context(self):
        workflow = default_workflow()

        rendered = {
            trigger: render_preview(workflow, trigger)
            for trigger in EVENT_TRIGGERS
        }

        self.assertEqual(set(rendered), set(EVENT_TRIGGERS))
        self.assertNotIn("{{", "".join(rendered.values()))

    def test_variable_catalog_exposes_every_planner_event_value(self):
        names = {
            row["name"]
            for row in build_variable_catalog(
                build_runtime_context_defaults(),
                default_workflow(),
            )
        }

        self.assertTrue(
            {
                "grid.name",
                "cleaning.cycle",
                "spiral.name",
                "runtime.spot.dispense_ul",
                "runtime.spot.theta",
                "runtime.spot.radius",
                "runtime.spot.continuous",
                "runtime.refill.container_id",
                "runtime.rinse.phase",
            }.issubset(names)
        )


class WorkflowRenderingTests(unittest.TestCase):
    def test_compiled_template_preserves_exact_rendered_output(self):
        template = (
            "prefix={{ global.movement_speed :08.3f }}"
            "|quoted={{ 'literal:colon' }}"
            "|empty={{ custom.empty }}"
            "|sum={{ global.movement_speed + 1 }}\n"
        )
        context = {
            "global": {"movement_speed": 3.125},
            "custom": {"empty": None},
        }
        expected = (
            "prefix=0003.125|quoted=literal:colon|empty=|sum=4.125\n"
        )

        self.assertEqual(render_template(template, context), expected)
        self.assertEqual(render_template(template, context).encode(), expected.encode())

        detached = workflow_module.template_expressions(template)
        detached.append(("custom.mutated", None))
        self.assertNotIn(
            ("custom.mutated", None),
            workflow_module.template_expressions(template),
        )

    def test_unformatted_floats_render_as_plain_decimal_gcode_numbers(self):
        rendered = render_template(
            "G0 X{{small}} F{{speed}}\n",
            {
                "small": 1e-6,
                "speed": 6e2,
            },
        )

        self.assertEqual(rendered, "G0 X0.000001 F600.0\n")
        self.assertNotRegex(rendered, r"\d[eE][-+]?\d")

    def test_template_formatting_arithmetic_and_condition(self):
        workflow = minimal_workflow(
            custom_variables=[custom_variable("increment", value=2.0)],
            condition="global.movement_speed > 0 and custom.increment == 2",
            template=(
                "speed={{global.movement_speed:.2f}} "
                "sum={{global.movement_speed + custom.increment:.1f}}\n"
            ),
        )
        engine = WorkflowEngine(
            workflow,
            base_context={"global": {"movement_speed": 3.14159}},
        )

        self.assertEqual(engine.emit("job_start"), "speed=3.14 sum=5.1\n")
        self.assertEqual(
            engine.emit("job_start", {"global": {"movement_speed": 0.0}}),
            "",
        )

    def test_custom_expression_resolves_custom_peer_and_runtime_namespace(self):
        workflow = minimal_workflow(
            custom_variables=[
                custom_variable("base", value=2.0),
                custom_variable(
                    "derived",
                    expression="custom.base * 2 + global.row_start_wait",
                ),
            ],
            template="derived={{custom.derived:.1f}}\n",
        )

        engine = WorkflowEngine(
            workflow,
            base_context={"global": {"row_start_wait": 0.5}},
        )

        self.assertEqual(engine.custom_values["derived"], 4.5)
        self.assertEqual(engine.emit("job_start"), "derived=4.5\n")

    def test_custom_expression_can_follow_event_runtime_values(self):
        workflow = minimal_workflow(
            custom_variables=[
                custom_variable("event_x", expression="runtime.spot.x * 2"),
            ],
            template="event_x={{custom.event_x:.1f}}\n",
        )
        workflow["blocks"][0]["sections"][0]["trigger"] = "grid_spot_move"
        engine = WorkflowEngine(
            workflow,
            base_context=build_runtime_context_defaults(),
        )

        self.assertEqual(
            engine.emit("grid_spot_move", {"runtime": {"spot": {"x": 3.25}}}),
            "event_x=6.5\n",
        )

    def test_custom_expression_cycle_is_rejected(self):
        workflow = minimal_workflow(
            custom_variables=[
                custom_variable("first", expression="custom.second + 1"),
                custom_variable("second", expression="custom.first + 1"),
            ]
        )

        with self.assertRaises(WorkflowValidationError) as raised:
            WorkflowEngine(workflow)
        self.assertIn("cycle", str(raised.exception).lower())

    def test_custom_expression_missing_variable_is_rejected(self):
        workflow = minimal_workflow(
            custom_variables=[
                custom_variable("derived", expression="runtime.not_available + 1"),
            ]
        )

        with self.assertRaises(WorkflowValidationError) as raised:
            WorkflowEngine(workflow, base_context={"runtime": {}})
        self.assertIn("not_available", str(raised.exception))

    def test_unrelated_event_custom_expression_is_resolved_lazily(self):
        workflow = minimal_workflow(
            custom_variables=[
                custom_variable("static_value", value=7.0),
                custom_variable("spot_value", expression="runtime.spot.x * 2"),
            ],
            template="value={{custom.static_value}}\n",
        )

        engine = WorkflowEngine(workflow, base_context={})

        self.assertEqual(engine.emit("job_start"), "value=7.0\n")

    def test_repeated_emit_reuses_compiled_expressions_and_trigger_indexes(self):
        workflow_module._rewrite_reserved_names.cache_clear()
        workflow_module._split_placeholder.cache_clear()
        workflow_module._compile_template.cache_clear()
        workflow_module._custom_dependencies_cached.cache_clear()
        workflow_module._expression_variable_paths_cached.cache_clear()
        workflow_module._EVALUATOR._parse_cached.cache_clear()

        workflow = minimal_workflow(
            custom_variables=[custom_variable("cache_probe", value=2.0)],
            condition="global.movement_speed > 0 and custom.cache_probe == 2",
            template=(
                "speed={{global.movement_speed:.2f}} "
                "sum={{global.movement_speed + custom.cache_probe:.1f}}\n"
            ),
        )
        engine = WorkflowEngine(
            workflow,
            base_context={"global": {"movement_speed": 3.14159}},
        )

        self.assertEqual(
            tuple(
                section["id"]
                for _block, section in engine._sections_by_trigger["job_start"]
            ),
            ("test-section",),
        )
        self.assertEqual(
            engine._custom_dependencies_by_trigger["job_start"],
            frozenset({"cache_probe"}),
        )

        expected = engine.emit("job_start")
        parse_after_first = workflow_module._EVALUATOR._parse_cached.cache_info()
        template_after_first = workflow_module._compile_template.cache_info()
        with mock.patch.object(
            workflow_module,
            "template_expressions",
            wraps=workflow_module.template_expressions,
        ) as template_scan:
            with mock.patch.object(
                workflow_module,
                "_expression_variable_paths",
                wraps=workflow_module._expression_variable_paths,
            ) as variable_scan:
                with mock.patch.object(
                    workflow_module,
                    "_custom_dependencies",
                    wraps=workflow_module._custom_dependencies,
                ) as dependency_scan:
                    repeated = [engine.emit("job_start") for _ in range(50)]

        parse_after_repeat = workflow_module._EVALUATOR._parse_cached.cache_info()
        template_after_repeat = workflow_module._compile_template.cache_info()
        self.assertEqual(repeated, [expected] * 50)
        self.assertEqual(parse_after_repeat.misses, parse_after_first.misses)
        self.assertGreater(parse_after_repeat.hits, parse_after_first.hits)
        self.assertEqual(template_after_repeat.misses, template_after_first.misses)
        self.assertGreater(template_after_repeat.hits, template_after_first.hits)
        template_scan.assert_not_called()
        variable_scan.assert_not_called()
        dependency_scan.assert_not_called()


class WorkflowValidationTests(unittest.TestCase):
    def test_unknown_trigger_and_variable_are_rejected(self):
        workflow = minimal_workflow(template="{{runtime.not_available}}")
        workflow["blocks"][0]["sections"][0]["trigger"] = "invented_event"

        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(workflow)

        message = str(raised.exception)
        self.assertIn("invented_event", message)
        self.assertIn("runtime.not_available", message)

    def test_event_scoped_values_are_limited_to_events_that_supply_them(self):
        workflow = minimal_workflow(template="theta={{runtime.spot.theta}}")
        section = workflow["blocks"][0]["sections"][0]
        section["trigger"] = "grid_spot_dispense"

        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(workflow)
        self.assertIn("outside its event scope", str(raised.exception))

        section["trigger"] = "spiral_drop"
        validate_workflow(workflow)

    def test_spot_value_cannot_be_used_before_a_spot_event(self):
        workflow = minimal_workflow(template="x={{runtime.spot.x}}")

        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(workflow)

        self.assertIn("outside its event scope", str(raised.exception))

    def test_required_planner_values_must_exist_and_be_positive(self):
        missing = minimal_workflow()
        missing["custom_variables"] = [
            variable
            for variable in missing["custom_variables"]
            if variable["name"] != "syringe_mm_per_ul"
        ]
        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(missing)
        self.assertIn("Missing required planner variable", str(raised.exception))

        nonpositive = minimal_workflow(
            custom_variables=[custom_variable("syringe_mm_per_ul", value=0.0)]
        )
        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(nonpositive)
        self.assertIn("positive number", str(raised.exception))

    def test_required_planner_value_cannot_depend_on_event_state(self):
        workflow = minimal_workflow(
            custom_variables=[
                custom_variable(
                    "syringe_mm_per_ul",
                    expression="runtime.spot.x + 1",
                )
            ]
        )

        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(workflow)

        self.assertIn("cannot depend on event-scoped variable", str(raised.exception))

    def test_nonfinite_custom_literal_is_rejected(self):
        workflow = minimal_workflow(
            custom_variables=[custom_variable("overflow", value=float("nan"))]
        )

        with self.assertRaises(WorkflowValidationError) as raised:
            validate_workflow(workflow)

        self.assertIn("finite number", str(raised.exception))

    def test_catalog_reports_exact_event_and_job_availability(self):
        catalog = {
            row["name"]: row
            for row in build_variable_catalog(
                build_runtime_context_defaults(),
                default_workflow(),
            )
        }

        self.assertEqual(catalog["spiral.center_x"]["job_kinds"], ["spiral"])
        self.assertEqual(catalog["grid.rows"]["job_kinds"], ["grid"])
        self.assertEqual(
            catalog["runtime.spot.theta"]["triggers"],
            ["spiral_continuous", "spiral_drop"],
        )
        self.assertNotIn(
            "grid_spot_dispense",
            catalog["runtime.spot.theta"]["triggers"],
        )
        self.assertEqual(
            catalog["cleaning.cycle"]["triggers"],
            [
                "cleaning_row_start",
                "cleaning_spot_dispense",
                "cleaning_spot_move",
                "cleaning_start",
            ],
        )


class WorkflowStoreTests(unittest.TestCase):
    def test_roundtrip_and_failed_save_preserve_previous_file(self):
        workflow = default_workflow()
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow_path = Path(temp_dir) / "workflow.json"
            store = WorkflowStore(workflow_path)

            saved_path = store.save(workflow)
            expected = validate_workflow(workflow)
            self.assertEqual(Path(saved_path), workflow_path)
            self.assertEqual(store.load(), expected)
            self.assertEqual(json.loads(workflow_path.read_text(encoding="utf-8")), expected)
            original_bytes = workflow_path.read_bytes()

            replacement = copy.deepcopy(workflow)
            replacement["name"] = "Replacement Workflow"
            with mock.patch(
                "app.gcode_workflow.os.replace",
                side_effect=OSError("simulated atomic replace failure"),
            ):
                with self.assertRaises(OSError):
                    store.save(replacement)

            self.assertEqual(workflow_path.read_bytes(), original_bytes)
            self.assertEqual(list(workflow_path.parent.glob("*.tmp")), [])

            invalid = copy.deepcopy(workflow)
            invalid["blocks"] = "not a block list"
            with self.assertRaises(WorkflowValidationError):
                store.save(invalid)

            self.assertEqual(workflow_path.read_bytes(), original_bytes)
            self.assertEqual(list(workflow_path.parent.glob("*.tmp")), [])


class HardcodedMachineCommandGuardTests(unittest.TestCase):
    def test_generation_sources_do_not_embed_workflow_machine_commands(self):
        forbidden_tokens = (
            "G0",
            "G1",
            "G21",
            "G28",
            "G90",
            "M117",
            "MESH",
            "BED_MESH",
            "MESH_CALIBRATE",
            "WAIT",
            "DISPENSE",
            "ASPIRATE",
            "PAUSE",
            "HOME_SYRINGE",
            "SET_GCODE_OFFSET",
            "SET_TMC_FIELD",
            "NEEDLE_TIP_OFFSETS_DISABLE",
            "NEEDLE_TIP_OFFSETS_ENABLE",
        )
        # This guard protects the generated-job architecture. Direct-control
        # modules legitimately name reviewed firmware entry-point macros and
        # UI actions such as Pause; they do not emit recipe lifecycle G-code.
        generation_modules = (
            "gcode_generation.py",
            "gcode_shared.py",
            "gcode_planner.py",
            "grid_gcode.py",
            "spiral_gcode.py",
        )
        source_paths = [
            PROJECT_DIR / "app" / module_name
            for module_name in generation_modules
        ]
        source_paths.extend(
            sorted((PROJECT_DIR / "app" / "plugins").rglob("*.py"))
        )

        violations = []
        for source_path in source_paths:
            source = source_path.read_text(encoding="utf-8")
            for line_number, line in enumerate(source.splitlines(), start=1):
                for token in forbidden_tokens:
                    if token in line:
                        violations.append(
                            f"{source_path.relative_to(PROJECT_DIR)}:{line_number}: {token}"
                        )

        self.assertEqual(
            violations,
            [],
            "Generated lifecycle commands must live in config/config_gcode_workflow.json:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
