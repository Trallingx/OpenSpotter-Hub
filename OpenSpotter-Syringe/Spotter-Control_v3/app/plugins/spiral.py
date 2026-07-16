"""Spiral geometry plugin for OpenSpotter-Syringe.

The plugin produces numeric point events.  The runtime workflow owns all machine
command text, keeping pattern geometry independent from the output language.
"""
from math import cos, pi, sin, sqrt


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _spiral_points(
    center_x,
    center_y,
    start_radius,
    turns,
    spacing_mm,
    resolution_radians,
    theta_offset=0.0,
):
    # Archimedean spiral: r = a + b*theta
    # b controls radial spacing per revolution.
    b = max(1e-9, spacing_mm / (2.0 * pi))
    max_theta = 2.0 * pi * max(0.0, turns)
    step = float(resolution_radians)
    if step <= 0:
        raise ValueError("Spiral resolution must be positive")

    points = []
    theta = 0.0
    while theta <= max_theta + 1e-9:
        adjusted_theta = theta + theta_offset
        radius = start_radius + b * theta
        x = center_x + radius * cos(adjusted_theta)
        y = center_y + radius * sin(adjusted_theta)
        points.append((x, y, adjusted_theta, radius))
        theta += step

    return points


def _interleave_point_sets(point_sets):
    max_len = max((len(points) for points in point_sets), default=0)
    for index in range(max_len):
        for points in point_sets:
            if index < len(points):
                yield points[index]


class SpiralPlugin:
    name = 'spiral'

    def plan(self, grid_context):
        params = grid_context.get('params', {}) or {}

        center_x = float(params.get('center_x', 0.0))
        center_y = float(params.get('center_y', 0.0))
        start_radius = float(params.get('start_radius', 0.0))
        turns = float(params.get('turns', 5.0))
        num_starts = max(1, int(params.get('num_starts', 1)))
        spacing_mm = float(params.get('spacing_mm', 1.5))
        dispense_vol_ul = float(params.get('dispense_vol', 0.003))
        if start_radius < 0:
            raise ValueError("Spiral start radius cannot be negative")
        if turns < 0:
            raise ValueError("Spiral turns cannot be negative")
        if spacing_mm <= 0:
            raise ValueError("Spiral spacing must be positive")
        if dispense_vol_ul < 0:
            raise ValueError("Spiral dispense volume cannot be negative")
        spiral_mode = str(params.get('spiral_mode', 'drop')).strip().lower()
        interleave = _as_bool(params.get('interleave', False))
        if spiral_mode == 'continuous' and interleave and num_starts > 1:
            raise ValueError(
                "Interleaving multiple starts is not supported in continuous spiral mode"
            )
        resolution_radians = float(grid_context['resolution_radians'])
        millimeters_per_microliter = float(grid_context['millimeters_per_microliter'])

        # Build one point set per start with equal angular offsets.
        point_sets = []
        for start_index in range(num_starts):
            theta_offset = (2.0 * pi * start_index) / float(num_starts)
            point_sets.append([
                (start_index, *point)
                for point in _spiral_points(
                    center_x=center_x,
                    center_y=center_y,
                    start_radius=start_radius,
                    turns=turns,
                    spacing_mm=spacing_mm,
                    resolution_radians=resolution_radians,
                    theta_offset=theta_offset,
                )
            ])

        if interleave:
            path = list(_interleave_point_sets(point_sets))
        else:
            path = [point for points in point_sets for point in points]

        if not path:
            return []

        planned_points = []
        previous_by_start = {}
        for index, (start_index, x, y, theta, radius) in enumerate(path):
            previous_point = previous_by_start.get(start_index)
            if spiral_mode == 'continuous' and previous_point is not None:
                dx = x - previous_point[0]
                dy = y - previous_point[1]
                segment_length = sqrt(dx * dx + dy * dy)
                segment_ul = max(dispense_vol_ul, segment_length * dispense_vol_ul)
                continuous = True
            else:
                segment_length = 0.0
                segment_ul = dispense_vol_ul
                continuous = False
            planned_points.append({
                'index': index,
                'start_index': start_index,
                'x': x,
                'y': y,
                'theta': theta,
                'radius': radius,
                'segment_length': segment_length,
                'dispense_ul': segment_ul,
                'dispense_mm': segment_ul * millimeters_per_microliter,
                'continuous': continuous,
            })
            previous_by_start[start_index] = (x, y)
        return planned_points


def register():
    return SpiralPlugin()
