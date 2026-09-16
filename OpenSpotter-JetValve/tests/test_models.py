"""
Unit tests for model classes.
"""

import pytest
from models import Valve, Gantry, Point3D, PrintJob, GridConfig, CalibrationOffset


class TestValve:
    """Test Valve model."""

    def test_valve_creation(self):
        """Test creating a valve."""
        valve = Valve(id=0, config={"pin": 12, "name": "Test Valve", "color": [255, 0, 0]})
        assert valve.id == 0
        assert valve.config["pin"] == 12
        assert valve.config["name"] == "Test Valve"
        assert valve.config["color"] == [255, 0, 0]

    def test_add_planned_line(self):
        """Test adding planned lines."""
        valve = Valve(id=0, config={"pin": 12})
        valve.add_planned_line(10.0, 20.0)
        valve.add_planned_line(30.0, 40.0)
        assert len(valve.lines_planned) == 2
        assert valve.lines_planned[0] == (10.0, 20.0)


class TestGantry:
    """Test Gantry model."""

    def test_gantry_creation(self):
        """Test creating a gantry."""
        gantry = Gantry()
        assert gantry.position == Point3D(0, 0, 0)
        assert gantry.velocity == 0.0

    def test_gantry_position_update(self):
        """Test updating gantry position."""
        gantry = Gantry()
        gantry.set_position(100, 100, 5)
        assert gantry.position.x == 100
        assert gantry.position.y == 100
        assert gantry.position.z == 5

    def test_gantry_limits(self):
        """Test gantry limit checking."""
        gantry = Gantry()
        point_valid = Point3D(100, 100, 5)
        point_invalid = Point3D(300, 300, 15)

        assert gantry.is_within_limits(point_valid)
        assert not gantry.is_within_limits(point_invalid)


class TestPrintJob:
    """Test PrintJob model."""

    def test_printjob_creation(self):
        """Test creating a print job."""
        job = PrintJob(job_id="job_001", num_lines=100)
        assert job.job_id == "job_001"
        assert job.num_lines == 100
        assert job.current_line == 0
        assert not job.is_complete()

    def test_progress_calculation(self):
        """Test progress percentage calculation."""
        job = PrintJob(num_lines=100)
        assert job.progress_percent == 0.0

        job.current_line = 50
        assert job.progress_percent == 50.0

        job.current_line = 100
        assert job.progress_percent == 100.0

    def test_advance_line(self):
        """Test advancing to next line."""
        job = PrintJob(num_lines=10)
        assert job.current_line == 0

        job.advance_line()
        assert job.current_line == 1

        # Advance to end
        for _ in range(9):
            job.advance_line()

        assert job.is_complete()
        assert not job.advance_line()  # Can't advance past end

    def test_add_valve(self):
        """Test adding valves to job."""
        job = PrintJob()
        valve = Valve(id=0, config={"pin": 12})
        job.add_valve(valve)

        assert len(job.valves) == 1
        assert job.get_valve(0) == valve


class TestGridConfig:
    """Test GridConfig model."""

    def test_grid_active_roundtrip(self):
        grid = GridConfig(name="Grid A", valve_id=2, active=False, config={"rows": 3})
        data = grid.to_dict()

        assert data["name"] == "Grid A"
        assert data["valve_id"] == 2
        assert data["active"] is False
        assert data["rows"] == 3

        restored = GridConfig.from_dict(data)
        assert restored.name == "Grid A"
        assert restored.valve_id == 2
        assert restored.active is False
        assert restored.config["rows"] == 3


class TestCalibrationOffset:
    """Test CalibrationOffset."""

    def test_offset_creation(self):
        """Test creating a calibration offset."""
        offset = CalibrationOffset(valve_id=0, spot_id=1, offset_x_um=10.0, offset_y_um=20.0)
        assert offset.valve_id == 0
        assert offset.spot_id == 1
        assert offset.offset_x_um == 10.0
        assert offset.offset_y_um == 20.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
