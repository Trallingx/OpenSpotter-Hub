import importlib.util
import math
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
TCP_MODULE_PATH = (
    PROJECT_DIR
    / "hardware"
    / "klipper"
    / "config"
    / "scripts"
    / "tcp_calibration.py"
)

SPEC = importlib.util.spec_from_file_location("tcp_calibration_under_test", TCP_MODULE_PATH)
TCP_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TCP_MODULE)


class TcpPositiveDownCoordinateTests(unittest.TestCase):
    def test_positive_down_calibration_uses_coordinate_version_two(self):
        self.assertEqual(TCP_MODULE.TCP_COORDINATE_VERSION, 2)
        self.assertIn("coordinate_version", TCP_MODULE.PERSISTED_RESULT_NAMES)

    def test_old_saved_tcp_calibration_is_rejected(self):
        calibration = TCP_MODULE.TCPCalibration.__new__(
            TCP_MODULE.TCPCalibration
        )
        calibration.printer = type(
            "Printer",
            (),
            {"command_error": staticmethod(RuntimeError)},
        )()
        calibration._get_saved_variables = lambda: {
            "tcp_ready": True,
            "tcp_coordinate_version": 1,
        }

        with self.assertRaisesRegex(RuntimeError, "coordinate version 2"):
            calibration._require_current_tcp_calibration()

    def test_reflected_normals_preserve_physical_beam_coordinates(self):
        old_x_normal = (math.sqrt(0.5), math.sqrt(0.5))
        old_y_normal = (-math.sqrt(0.5), math.sqrt(0.5))
        old_point = (23.0, -17.0)
        reflected_point = (old_point[0], -old_point[1])

        old_x_coord = sum(a * b for a, b in zip(old_x_normal, old_point))
        old_y_coord = sum(a * b for a, b in zip(old_y_normal, old_point))
        new_x_coord = sum(
            a * b
            for a, b in zip(TCP_MODULE.DEFAULT_X_BEAM_NORMAL, reflected_point)
        )
        new_y_coord = sum(
            a * b
            for a, b in zip(TCP_MODULE.DEFAULT_Y_BEAM_NORMAL, reflected_point)
        )

        self.assertAlmostEqual(new_x_coord, old_x_coord)
        self.assertAlmostEqual(new_y_coord, old_y_coord)

    def test_reflected_y_direction_keeps_the_same_physical_first_sweep(self):
        old_x_normal = (math.sqrt(0.5), math.sqrt(0.5))
        old_beam_direction = (old_x_normal[1], -old_x_normal[0])
        reflected_old_sweep = (
            old_beam_direction[0],
            -old_beam_direction[1],
        )

        new_x_normal = TCP_MODULE.DEFAULT_X_BEAM_NORMAL
        new_beam_direction = (new_x_normal[1], -new_x_normal[0])
        new_first_sweep = tuple(
            component * TCP_MODULE.DEFAULT_Y_DIRECTION
            for component in new_beam_direction
        )

        self.assertAlmostEqual(new_first_sweep[0], reflected_old_sweep[0])
        self.assertAlmostEqual(new_first_sweep[1], reflected_old_sweep[1])

    def test_positive_down_normals_round_trip_an_xy_intersection(self):
        calibration = TCP_MODULE.TCPCalibration.__new__(
            TCP_MODULE.TCPCalibration
        )
        calibration.x_normal = TCP_MODULE.DEFAULT_X_BEAM_NORMAL
        calibration.y_normal = TCP_MODULE.DEFAULT_Y_BEAM_NORMAL
        point = (41.25, 78.5)

        x_coord = calibration._beam_coord(calibration.x_normal, point)
        y_coord = calibration._beam_coord(calibration.y_normal, point)

        recovered = calibration._xy_from_beam_coords(x_coord, y_coord)
        self.assertAlmostEqual(recovered[0], point[0])
        self.assertAlmostEqual(recovered[1], point[1])


if __name__ == "__main__":
    unittest.main()
