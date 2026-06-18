"""Spiral grid plugin for UniSpotter_v3.

Supports two output modes:
- drop: emit single droplets along the spiral path
- continuous: emit many short segments with dispensing on each segment

The implementation is intentionally self-contained so it can be used as a template
for additional plugin modes.
"""
from math import atan2, cos, pi, sin, sqrt


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _spiral_points(center_x, center_y, start_radius, turns, spacing_mm, theta_offset=0.0):
    # Archimedean spiral: r = a + b*theta
    # b controls radial spacing per revolution.
    b = max(1e-9, spacing_mm / (2.0 * pi))
    max_theta = 2.0 * pi * max(0.0, turns)
    step = 0.08

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

    def fields(self):
        return [
            ('center_x', 0.0),
            ('center_y', 0.0),
            ('start_radius', 0.0),
            ('turns', 5.0),
            ('num_starts', 1),
            ('spacing_mm', 1.5),
            ('dispense_vol', 0.003),
            ('spiral_mode', 'drop'),
            ('interleave', False),
        ]

    def generate(self, file, settings, grid_context):
        params = grid_context.get('params', {}) or {}
        helpers = grid_context.get('helpers', {}) or {}
        volume_to_mm = helpers.get('volume_to_mm')
        if not callable(volume_to_mm):
            raise ValueError('grid_context.helpers.volume_to_mm is required')

        center_x = float(params.get('center_x', 0.0))
        center_y = float(params.get('center_y', 0.0))
        start_radius = float(params.get('start_radius', 0.0))
        turns = float(params.get('turns', 5.0))
        num_starts = max(1, int(params.get('num_starts', 1)))
        spacing_mm = float(params.get('spacing_mm', 1.5))
        dispense_vol_ul = float(params.get('dispense_vol', 0.003))
        spiral_mode = str(params.get('spiral_mode', 'drop')).strip().lower()
        interleave = _as_bool(params.get('interleave', False))
        movement_speed = float(grid_context.get('speed', 5000))
        dispensing_speed = float(grid_context.get('dispensing_speed', 500))
        z_high = grid_context.get('z_high')
        z_low = grid_context.get('z_low')

        # Build one point set per start with equal angular offsets.
        point_sets = []
        for start_index in range(num_starts):
            theta_offset = (2.0 * pi * start_index) / float(num_starts)
            point_sets.append(
                _spiral_points(
                    center_x=center_x,
                    center_y=center_y,
                    start_radius=start_radius,
                    turns=turns,
                    spacing_mm=spacing_mm,
                    theta_offset=theta_offset,
                )
            )

        if interleave:
            path = list(_interleave_point_sets(point_sets))
        else:
            path = [point for points in point_sets for point in points]

        if not path:
            return {'total_dispense_uL': 0.0, 'spots_count': 0, 'mode': spiral_mode}

        file.write('\n; Spiral sequence\n')
        file.write(f'M117; Spiral {spiral_mode}\n')

        spots = 0
        total_dispense_ul = 0.0
        previous_point = None
        for x, y, theta, radius in path:
            if spiral_mode == 'continuous' and previous_point is not None:
                dx = x - previous_point[0]
                dy = y - previous_point[1]
                segment_length = sqrt(dx * dx + dy * dy)
                # Approximate volume proportional to segment length. The caller can tune this value.
                segment_ul = max(dispense_vol_ul, segment_length * dispense_vol_ul)
                file.write(f'G1 X{x:.3f} Y{y:.3f} F{movement_speed}\n')
                file.write(f'DISPENSE MM={volume_to_mm(segment_ul):.6f} SPEED={dispensing_speed} RELATIVE=1\n')
                total_dispense_ul += segment_ul
            else:
                file.write(f'G0 X{x:.3f} Y{y:.3f} F{movement_speed}\n')
                file.write(f'DISPENSE MM={volume_to_mm(dispense_vol_ul):.6f} SPEED={dispensing_speed} RELATIVE=1\n')
                total_dispense_ul += dispense_vol_ul
            previous_point = (x, y)
            spots += 1

        return {
            'total_dispense_uL': total_dispense_ul,
            'spots_count': spots,
            'mode': spiral_mode,
            'num_starts': num_starts,
        }


def register():
    return SpiralPlugin()
