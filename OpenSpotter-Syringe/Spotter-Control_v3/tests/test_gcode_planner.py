import copy
import io
import unittest
from collections import Counter
from math import pi
from types import SimpleNamespace

from app.SpotterFunctions import create_coordinates, entries_to_dict
from app.gcode_planner import empty_syringe, generate_grid_events, generate_spiral_events
from app.input_configs import Field
from app.plugins.spiral import SpiralPlugin


class RecordingEngine:
    def __init__(self, millimeters_per_microliter=1.0):
        self.custom_values = {"syringe_mm_per_ul": millimeters_per_microliter}
        self.events = []

    def emit(self, trigger, overrides):
        self.events.append((trigger, copy.deepcopy(overrides)))
        return f"<{trigger}>\n"


class CoordinatePlannerTests(unittest.TestCase):
    def test_create_coordinates_returns_numeric_row_major_points(self):
        coordinates = create_coordinates(
            rows=2,
            cols=3,
            x_offset=10.0,
            grid_x_offset=0.5,
            x_shift=2.0,
            y_offset=20.0,
            grid_y_offset=-1.0,
            y_shift=3.0,
        )

        self.assertEqual(
            coordinates,
            [
                (10.5, 19.0),
                (12.5, 19.0),
                (14.5, 19.0),
                (10.5, 22.0),
                (12.5, 22.0),
                (14.5, 22.0),
            ],
        )
        self.assertTrue(
            all(isinstance(axis, (int, float)) for point in coordinates for axis in point)
        )

    def test_schema_values_keep_numeric_boolean_and_string_types(self):
        class Entry:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        fields = [
            Field("speed", "Speed", "mm/s"),
            Field("count", "Count", "int", default=1),
            Field("enabled", "Enabled", "bool", default=False),
            Field("mode", "Mode", "str", default="drop"),
        ]

        values = entries_to_dict(
            [Entry("12.5"), Entry("3.0"), Entry("False"), Entry("continuous")],
            fields,
        )

        self.assertEqual(
            values,
            {"speed": 12.5, "count": 3, "enabled": False, "mode": "continuous"},
        )


class GridEventPlannerTests(unittest.TestCase):
    def test_two_by_two_grid_refills_and_cleans_at_configured_cadence(self):
        engine = RecordingEngine()
        output = io.StringIO()
        syringe_tracker = [0.0]
        cleaning_cycle_counter = [0]
        washing_spot_counter = [0]
        common = {
            "x_offset": 10.0,
            "y_offset": 20.0,
            "priming_vol": 0.0,
        }
        grid_values = {
            "rows": 2,
            "cols": 2,
            "pitch_x": 2.0,
            "pitch_y": 3.0,
            "grid_offset_x": 0.5,
            "grid_offset_y": 1.0,
            "dispense_vol": 1.0,
            "row_add_volume": 0.0,
            "loading_from": 1,
        }
        cleaning_values = {
            "rows_cleaning": 1,
            "cols_cleaning": 1,
            "grid_offset_x_cleaning": 100.0,
            "grid_offset_y_cleaning": 50.0,
            "pitch_x_cleaning": 1.0,
            "pitch_y_cleaning": 1.0,
            "dispense_vol_cleaning": 0.25,
            "x_relative_increase": 0.0,
            "y_relative_increase": 0.0,
            "spots_before_cleaning": 2,
        }
        washing_values = {"washing_after_x_spots": 0}
        flags = {
            "cleaning_enabled": True,
            "washing_enabled": False,
            "wash_after_loading": False,
        }
        containers = {
            1: SimpleNamespace(x=1.0, y=2.0, z_filling_height=3.0),
        }

        spot_count = generate_grid_events(
            output,
            engine,
            common,
            grid_values,
            cleaning_values,
            washing_values,
            flags,
            containers,
            refill_ul=2.5,
            washing_spot_counter=washing_spot_counter,
            syringe_tracker=syringe_tracker,
            cleaning_cycle_counter=cleaning_cycle_counter,
        )

        triggers = [trigger for trigger, _context in engine.events]
        counts = Counter(triggers)
        self.assertEqual(spot_count, 4)
        self.assertEqual(counts["syringe_reload"], 2)
        self.assertEqual(counts["grid_start"], 1)
        self.assertEqual(counts["grid_spot_move"], 4)
        self.assertEqual(counts["grid_row_start"], 2)
        self.assertEqual(counts["grid_spot_dispense"], 4)
        self.assertEqual(counts["cleaning_start"], 4)
        self.assertEqual(counts["cleaning_spot_move"], 4)
        self.assertEqual(counts["cleaning_row_start"], 4)
        self.assertEqual(counts["cleaning_spot_dispense"], 4)
        self.assertEqual(cleaning_cycle_counter, [4])
        self.assertEqual(syringe_tracker, [0.0])

        self.assertEqual(
            triggers[:6],
            [
                "syringe_reload",
                "cleaning_start",
                "cleaning_spot_move",
                "cleaning_row_start",
                "cleaning_spot_dispense",
                "grid_start",
            ],
        )
        refill_contexts = [
            context["runtime"]["refill"]
            for trigger, context in engine.events
            if trigger == "syringe_reload"
        ]
        self.assertTrue(all(context["dynamic"] for context in refill_contexts))
        self.assertEqual([context["target_fill_mm"] for context in refill_contexts], [2.5, 2.5])

        spots = [
            context["runtime"]["spot"]
            for trigger, context in engine.events
            if trigger == "grid_spot_move"
        ]
        self.assertEqual(
            [(spot["x"], spot["y"]) for spot in spots],
            [(10.5, 21.0), (12.5, 21.0), (10.5, 24.0), (12.5, 24.0)],
        )
        self.assertEqual([spot["is_row_start"] for spot in spots], [True, False, True, False])

    def test_print_spot_larger_than_refill_cap_is_rejected(self):
        engine = RecordingEngine()

        with self.assertRaisesRegex(
            ValueError,
            "print spot exceeds the configured refill capacity",
        ):
            generate_grid_events(
                io.StringIO(),
                engine,
                {
                    "x_offset": 0.0,
                    "y_offset": 0.0,
                    "priming_vol": 0.0,
                    "drop_extra_aspirate": 0.0,
                },
                {
                    "rows": 1,
                    "cols": 1,
                    "pitch_x": 1.0,
                    "pitch_y": 1.0,
                    "grid_offset_x": 0.0,
                    "grid_offset_y": 0.0,
                    "dispense_vol": 1.1,
                    "row_add_volume": 0.0,
                    "loading_from": 1,
                },
                {},
                {},
                {
                    "cleaning_enabled": False,
                    "washing_enabled": False,
                    "wash_after_loading": False,
                },
                {1: SimpleNamespace(x=1.0, y=2.0, z_filling_height=3.0)},
                refill_ul=1.0,
            )

        self.assertEqual(engine.events, [])

    def test_cleaning_grid_plus_print_spot_larger_than_refill_cap_is_rejected(self):
        engine = RecordingEngine()

        with self.assertRaisesRegex(
            ValueError,
            "Cleaning grid plus one print spot exceeds the refill capacity",
        ):
            generate_grid_events(
                io.StringIO(),
                engine,
                {
                    "x_offset": 0.0,
                    "y_offset": 0.0,
                    "priming_vol": 0.0,
                    "drop_extra_aspirate": 0.0,
                },
                {
                    "rows": 1,
                    "cols": 1,
                    "pitch_x": 1.0,
                    "pitch_y": 1.0,
                    "grid_offset_x": 0.0,
                    "grid_offset_y": 0.0,
                    "dispense_vol": 0.6,
                    "row_add_volume": 0.0,
                    "loading_from": 1,
                },
                {
                    "rows_cleaning": 1,
                    "cols_cleaning": 1,
                    "dispense_vol_cleaning": 0.5,
                },
                {},
                {
                    "cleaning_enabled": True,
                    "washing_enabled": False,
                    "wash_after_loading": False,
                },
                {1: SimpleNamespace(x=1.0, y=2.0, z_filling_height=3.0)},
                refill_ul=1.0,
            )

        self.assertEqual(engine.events, [])


class SpiralEventPlannerTests(unittest.TestCase):
    def test_spiral_automatically_refills_when_total_exceeds_capacity(self):
        engine = RecordingEngine()
        syringe_tracker = [0.0]
        points = [
            {
                "index": index,
                "start_index": 0,
                "x": float(index),
                "y": 0.0,
                "dispense_ul": 0.4,
                "dispense_mm": 0.4,
                "continuous": False,
            }
            for index in range(4)
        ]

        result = generate_spiral_events(
            io.StringIO(),
            engine,
            {
                "max_syringe_vol": 1.0,
                "priming_vol": 0.0,
                "drop_extra_aspirate": 0.0,
            },
            {"spiral_mode": "drop"},
            points,
            SimpleNamespace(x=1.0, y=2.0, z_filling_height=3.0),
            loading_container_id=1,
            syringe_tracker=syringe_tracker,
        )

        reloads = [
            context["runtime"]["refill"]
            for trigger, context in engine.events
            if trigger == "syringe_reload"
        ]
        self.assertEqual(len(reloads), 2)
        self.assertEqual(
            [(reload["reason"], reload["dynamic"]) for reload in reloads],
            [("spiral_start", False), ("automatic_refill", True)],
        )
        self.assertEqual(
            [trigger for trigger, _context in engine.events].count("spiral_drop"),
            4,
        )
        self.assertAlmostEqual(syringe_tracker[0], 0.2)
        self.assertEqual(result["spots_count"], 4)
        self.assertAlmostEqual(result["total_dispense_uL"], 1.6)

    def test_continuous_spiral_repositions_after_an_automatic_refill(self):
        engine = RecordingEngine()
        points = [
            {
                "index": index,
                "start_index": 0,
                "x": float(index),
                "y": 0.0,
                "dispense_ul": 0.6,
                "dispense_mm": 0.6,
                "continuous": index > 0,
            }
            for index in range(3)
        ]

        generate_spiral_events(
            io.StringIO(),
            engine,
            {
                "max_syringe_vol": 1.2,
                "priming_vol": 0.0,
                "drop_extra_aspirate": 0.0,
            },
            {"spiral_mode": "continuous"},
            points,
            SimpleNamespace(x=1.0, y=2.0, z_filling_height=3.0),
            loading_container_id=1,
        )

        spot_triggers = [
            trigger
            for trigger, _context in engine.events
            if trigger in ("spiral_drop", "spiral_continuous")
        ]
        self.assertEqual(
            spot_triggers,
            ["spiral_drop", "spiral_continuous", "spiral_drop"],
        )


class SpiralGeometryTests(unittest.TestCase):
    def test_continuous_multi_start_tracks_each_start_independently(self):
        points = SpiralPlugin().plan(
            {
                "params": {
                    "center_x": 10.0,
                    "center_y": 20.0,
                    "start_radius": 1.0,
                    "turns": 0.25,
                    "num_starts": 2,
                    "spacing_mm": 1.0,
                    "dispense_vol": 0.1,
                    "spiral_mode": "continuous",
                    "interleave": False,
                },
                "resolution_radians": pi / 4.0,
                "millimeters_per_microliter": 1.0,
            }
        )

        by_start = {
            start_index: [
                point for point in points if point["start_index"] == start_index
            ]
            for start_index in (0, 1)
        }
        self.assertEqual([len(by_start[index]) for index in (0, 1)], [3, 3])
        for start_points in by_start.values():
            self.assertFalse(start_points[0]["continuous"])
            self.assertEqual(start_points[0]["segment_length"], 0.0)
            self.assertTrue(all(point["continuous"] for point in start_points[1:]))
            self.assertTrue(all(point["segment_length"] > 0.0 for point in start_points[1:]))

        second_start_index = next(
            index for index, point in enumerate(points) if point["start_index"] == 1
        )
        self.assertFalse(points[second_start_index]["continuous"])
        self.assertEqual(points[second_start_index]["segment_length"], 0.0)

    def test_interleaved_continuous_multi_start_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Interleaving multiple starts is not supported in continuous spiral mode",
        ):
            SpiralPlugin().plan(
                {
                    "params": {
                        "num_starts": 2,
                        "spiral_mode": "continuous",
                        "interleave": True,
                    },
                    "resolution_radians": 0.1,
                    "millimeters_per_microliter": 1.0,
                }
            )


class EmptySyringePlannerTests(unittest.TestCase):
    def test_final_rinse_end_event_reports_completed_cycle_and_phase(self):
        engine = RecordingEngine()
        syringe_tracker = [12.0]

        empty_syringe(
            io.StringIO(),
            engine,
            {
                "max_syringe_mm": 50.0,
                "min_syringe_mm": 2.0,
            },
            SimpleNamespace(x=1.0, y=2.0, z_filling_height=3.0),
            container_id=4,
            final_rinse_enabled=True,
            rinsing_cycles=3,
            syringe_tracker=syringe_tracker,
        )

        rinse_cycles = [
            context["runtime"]["rinse"]
            for trigger, context in engine.events
            if trigger == "rinse_cycle"
        ]
        self.assertEqual(
            [(rinse["phase"], rinse["cycle"]) for rinse in rinse_cycles],
            [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)],
        )
        end_context = next(
            context["runtime"]["rinse"]
            for trigger, context in engine.events
            if trigger == "syringe_empty_end"
        )
        self.assertEqual(end_context["phase"], 2)
        self.assertEqual(end_context["cycle"], 3)
        self.assertEqual(syringe_tracker, [0.0])


if __name__ == "__main__":
    unittest.main()
