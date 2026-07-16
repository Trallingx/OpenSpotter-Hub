# Continuous optical-cross TCP calibration.
#
# This module uses Klipper's MCU endstop homing path so calibration moves can
# stop on beam transitions without the jitter of macro-level polling.
#
# Important movement model:
#   Klipper's homing/probing stop-on-endstop path operates on one straight move
#   at a time. This module therefore does not trace the old macro's circle.
#   Instead, the needle is deliberately placed to one side of the optical cross,
#   then the module performs:
#     1. one pure-X acquisition sweep until the X beam is hit,
#     2. diagonal sweeps normal to the X beam while stepping upward in Z, so a
#        bent needle can be re-centered until its tip clears the beam,
#     3. a return to tip Z minus 2 mm, where both beam coordinates are measured
#        in one common plane,
#     4. X centering normal to X, followed by Y centering while moving along X,
#     5. XY recovery from those same-plane beam coordinates,
#     6. sequential X/Y state queries without movement; calibration succeeds
#        only when the centered needle disrupts both beams.

import math


# Beam normals define the coordinate measured by each beam. They are
# perpendicular to the physical beam lines:
#   physical X beam line: rises toward X- (-45 degrees)
#   physical Y beam line: rises toward X+ (+45 degrees)
#
# The default values preserve the physical 45-degree optical cross after the
# machine Y basis is reflected so positive Y points down in the top view:
#   x_beam_coord = ( x - y) / sqrt(2)
#   y_beam_coord = (-x - y) / sqrt(2)
DEFAULT_X_BEAM_NORMAL = (0.70710678118, -0.70710678118)
DEFAULT_Y_BEAM_NORMAL = (-0.70710678118, -0.70710678118)
DEFAULT_X_DIRECTION = -1.0
DEFAULT_Y_DIRECTION = -1.0
TCP_COORDINATE_VERSION = 2
TIP_SEARCH_EPSILON = 0.000001
FINAL_CENTER_Z_DROP = 2.0
PERSISTED_RESULT_NAMES = (
    'tip_x', 'tip_y', 'tip_z',
    'expected_x', 'expected_y', 'expected_z',
    'offset_x', 'offset_y', 'offset_z')


def _direction_sign(value, name, error):
    """Validate a configured direction and reduce it to -1 or +1."""
    if not value:
        raise error("%s can not be zero" % (name,))
    return -1.0 if value < 0.0 else 1.0


def _is_missing_trigger(error):
    """Identify Klipper's normal end-of-scan result without hiding faults."""
    return str(error).startswith("No trigger on ")


class TCPBeam:
    """Small wrapper around an optical beam input configured as an endstop."""

    def __init__(self, config, name, pin):
        self.printer = config.get_printer()
        self.name = name
        ppins = self.printer.lookup_object('pins')
        self.mcu_endstop = ppins.setup_pin('endstop', pin)
        self.printer.register_event_handler(
            'klippy:mcu_identify', self._handle_mcu_identify)

    def _handle_mcu_identify(self):
        # Homing-style endstop stops only work when the endstop is associated
        # with the steppers that may move during the scan. Attach XYZ so both
        # XY line scans and Z edge scans can stop on the beam.
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if (stepper.is_active_axis('x') or stepper.is_active_axis('y')
                    or stepper.is_active_axis('z')):
                self.mcu_endstop.add_stepper(stepper)


class TCPCalibration:
    """Klipper extra that finds a needle tip with two optical beams."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.toolhead = None
        self.homing = None

        self.x_beam = TCPBeam(config, 'tcp_beam_x', config.get('x_pin'))
        self.y_beam = TCPBeam(config, 'tcp_beam_y', config.get('y_pin'))
        self.x_normal = self._normalize(config.getfloatlist(
            'x_beam_normal', DEFAULT_X_BEAM_NORMAL, count=2))
        self.y_normal = self._normalize(config.getfloatlist(
            'y_beam_normal', DEFAULT_Y_BEAM_NORMAL, count=2))
        self._check_normals()

        self.default_xy_travel = config.getfloat('xy_travel', 2.0, above=0.)
        self.default_x_sweep_travel = config.getfloat(
            'x_sweep_travel', 10.0, above=0.)
        self.default_y_sweep_travel = config.getfloat(
            'y_sweep_travel', 10.0, above=0.)
        self.default_x_direction = _direction_sign(
            config.getfloat('x_direction', DEFAULT_X_DIRECTION),
            'tcp_calibration x_direction', config.error)
        self.default_y_direction = _direction_sign(
            config.getfloat('y_direction', DEFAULT_Y_DIRECTION),
            'tcp_calibration y_direction', config.error)
        self.default_xy_passes = config.getint('xy_passes', 2, minval=1)
        self.default_speed = config.getfloat('speed', 5.0, above=0.)
        self.default_z_speed = config.getfloat('z_speed', 1.0, above=0.)
        self.default_z_travel = config.getfloat('z_travel', 4.0, above=0.)
        self.default_z_step = config.getfloat('z_step', 2.0, above=0.)
        self.default_z_tolerance = config.getfloat(
            'z_tolerance', 0.01, above=0.)
        self.require_bltouch_parked = config.getboolean(
            'require_bltouch_parked', True)

        self.last_result = {}
        self.gcode.register_command(
            'TCPCALIBRATE', self.cmd_TCPCALIBRATE,
            desc=self.cmd_TCPCALIBRATE_help)
        self.gcode.register_command(
            'TCPQUERYBEAMS', self.cmd_TCPQUERYBEAMS,
            desc=self.cmd_TCPQUERYBEAMS_help)
        self.gcode.register_command(
            'TCPQUERYBLTOUCH', self.cmd_TCPQUERYBLTOUCH,
            desc=self.cmd_TCPQUERYBLTOUCH_help)
        self.gcode.register_command(
            'TCPSHOWOFFSETS', self.cmd_TCPSHOWOFFSETS,
            desc=self.cmd_TCPSHOWOFFSETS_help)
        self.gcode.register_command(
            'TCPMOVEWITHOFFSET', self.cmd_TCPMOVEWITHOFFSET,
            desc=self.cmd_TCPMOVEWITHOFFSET_help)

    def _lookup_runtime_objects(self):
        if self.toolhead is None:
            self.toolhead = self.printer.lookup_object('toolhead')
        if self.homing is None:
            self.homing = self.printer.lookup_object('homing')

    def _normalize(self, vec):
        # Config values are user-facing, so normalize them once and let users
        # enter either unit vectors or any proportional vector.
        x, y = float(vec[0]), float(vec[1])
        length = math.hypot(x, y)
        if not length:
            raise self.printer.config_error("TCP beam normal can not be zero")
        return x / length, y / length

    def _check_normals(self):
        det = self._det()
        if abs(det) < 0.001:
            raise self.printer.config_error(
                "TCP beam normals must not be parallel")

    def _det(self):
        return (self.x_normal[0] * self.y_normal[1]
                - self.x_normal[1] * self.y_normal[0])

    def _require_homed(self):
        self._lookup_runtime_objects()
        eventtime = self.printer.get_reactor().monotonic()
        homed = self.toolhead.get_status(eventtime)['homed_axes']
        missing = [axis.upper() for axis in 'xyz' if axis not in homed]
        if missing:
            raise self.printer.command_error(
                "TCPCALIBRATE requires homed axes: missing %s"
                % (",".join(missing),))

    def _query_beam(self, beam):
        # Return the logical beam state after pin inversion. With ^! active-low
        # wiring, True means "beam disrupted" / PRESSED.
        self._lookup_runtime_objects()
        print_time = self.toolhead.get_last_move_time()
        return bool(beam.mcu_endstop.query_endstop(print_time))

    def _beam_normal(self, beam):
        if beam is self.x_beam:
            return self.x_normal
        return self.y_normal

    def _physical_beam_direction(self, beam):
        # Rotating a beam normal by 90 degrees gives a direction along the beam.
        # For the default cross, X rises toward X- and is also normal to Y.
        nx, ny = self._beam_normal(beam)
        return ny, -nx

    def _beam_coord(self, normal, pos):
        # Project a toolhead XY point onto a beam normal. A physical beam is
        # modeled as all XY points with the same projected coordinate.
        return normal[0] * pos[0] + normal[1] * pos[1]

    def _xy_from_beam_coords(self, x_coord, y_coord):
        # Recover the XY intersection of the two calibrated beam-coordinate
        # lines by solving the 2x2 linear system formed by the beam normals.
        det = self._det()
        nx1, ny1 = self.x_normal
        nx2, ny2 = self.y_normal
        x = (x_coord * ny2 - ny1 * y_coord) / det
        y = (nx1 * y_coord - x_coord * nx2) / det
        return x, y

    def _manual_move(self, coord, speed):
        self._lookup_runtime_objects()
        self.toolhead.manual_move(coord, speed)

    def _probe_to(self, beam, target, speed):
        # This is the core continuous-motion call. It performs one straight
        # homing move and lets the MCU stop it when the beam is disrupted.
        self._lookup_runtime_objects()
        return self.homing.manual_home(
            self.toolhead, [(beam.mcu_endstop, beam.name)], target, speed,
            probe_pos=True, triggered=True, check_triggered=True)

    def _move_to_xy(self, x, y, z, speed):
        self._manual_move([x, y, z], speed)

    def _scan_line_edge(self, beam, start_xy, target_xy, z, speed, gcmd,
                        label, travel_hint='XY_TRAVEL'):
        # Move to a clear start point first. This positioning move is not the
        # measurement; the following _probe_to() line is the monitored move.
        # If the visible crossing happens during this positioning move, increase
        # the relevant travel setting so the monitored line brackets the edge.
        self._move_to_xy(start_xy[0], start_xy[1], z, speed)
        if self._query_beam(beam):
            raise self.printer.command_error(
                "%s is already triggered at %s scan start. Increase "
                "%s or move the approximate beam point closer to the beam "
                "center." % (beam.name, label, travel_hint))
        target = list(self.toolhead.get_position())
        target[0] = target_xy[0]
        target[1] = target_xy[1]
        target[2] = z
        gcmd.respond_info(
            "TCP: %s %s straight scan X%.6f Y%.6f -> X%.6f Y%.6f at Z%.6f"
            % (beam.name, label, start_xy[0], start_xy[1],
               target_xy[0], target_xy[1], z))
        try:
            return self._probe_to(beam, target, speed)
        except self.printer.command_error as e:
            raise self.printer.command_error(
                "%s while scanning %s during %s from X%.6f Y%.6f to "
                "X%.6f Y%.6f. "
                "The monitored move is a straight line, not a circle. If the "
                "beam visibly crossed during the previous positioning move, "
                "increase %s or adjust the approximate point. If it "
                "crossed during this straight scan, run TCPQUERYBEAMS while "
                "manually blocking the beam to verify pin/invert state."
                % (str(e), beam.name, label, start_xy[0], start_xy[1],
                   target_xy[0], target_xy[1], travel_hint))

    def _scan_beam_center_on_line(self, beam, line_dir, approximate_xy, z,
                                  travel, speed, passes, gcmd, label):
        # Measure one optical beam by crossing it from both sides on a chosen
        # straight line. Averaging the two trigger points estimates the beam
        # center and cancels much of the beam-width / hysteresis error.
        line_dir = self._normalize(line_dir)
        normal = self._beam_normal(beam)
        coord_total = x_total = y_total = 0.0
        start_neg = (approximate_xy[0] - line_dir[0] * travel,
                     approximate_xy[1] - line_dir[1] * travel)
        start_pos = (approximate_xy[0] + line_dir[0] * travel,
                     approximate_xy[1] + line_dir[1] * travel)
        for sample in range(passes):
            edge_a = self._scan_line_edge(
                beam, start_neg, start_pos, z, speed, gcmd, label)
            edge_b = self._scan_line_edge(
                beam, start_pos, start_neg, z, speed, gcmd, label)
            coord_a = self._beam_coord(normal, edge_a)
            coord_b = self._beam_coord(normal, edge_b)
            beam_coord = 0.5 * (coord_a + coord_b)
            center_xy = (0.5 * (edge_a[0] + edge_b[0]),
                         0.5 * (edge_a[1] + edge_b[1]))
            coord_total += beam_coord
            x_total += center_xy[0]
            y_total += center_xy[1]
            gcmd.respond_info(
                "TCP: %s %s sample %d/%d coords %.6f %.6f -> %.6f"
                % (beam.name, label, sample + 1, passes, coord_a,
                   coord_b, beam_coord))
        avg_coord = coord_total / passes
        avg_point = (x_total / passes, y_total / passes)
        return avg_coord, avg_point

    def _acquire_x_beam_from_current_x(self, z, x_direction, travel, speed,
                                       gcmd):
        # The operator jogs the needle to the chosen safe side of the optical
        # cross. From that exact XY point we move only in X until the X beam
        # trips.
        pos = self.toolhead.get_position()
        start_xy = (pos[0], pos[1])
        for beam in (self.x_beam, self.y_beam):
            if self._query_beam(beam):
                raise self.printer.command_error(
                    "%s is already triggered before the first X sweep. Jog "
                    "the needle to the clear right/start side of the optical "
                    "cross or verify the beam input with TCPQUERYBEAMS."
                    % (beam.name,))
        target_xy = (pos[0] + x_direction * travel, pos[1])
        return self._scan_line_edge(
            self.x_beam, start_xy, target_xy, z, speed, gcmd,
            "initial X acquisition", "X_SWEEP_TRAVEL")

    def _acquire_y_beam_along_x_beam(self, x_center_xy, z, y_direction,
                                     travel, speed, gcmd):
        # Following the physical X beam preserves its measured coordinate while
        # crossing Y almost orthogonally. Only Y is monitored during movement.
        x_beam_dir = self._physical_beam_direction(self.x_beam)
        first_dir = (x_beam_dir[0] * y_direction,
                     x_beam_dir[1] * y_direction)
        self._move_to_xy(x_center_xy[0], x_center_xy[1], z, speed)
        if self._query_beam(self.y_beam):
            edge = list(self.toolhead.get_position())
            gcmd.respond_info(
                "TCP: %s already triggered while centered on X beam; using "
                "that point as the approximate Y-beam location"
                % (self.y_beam.name,))
        else:
            errors = []
            directions = (first_dir, (-first_dir[0], -first_dir[1]))
            for attempt, direction in enumerate(directions):
                target_xy = (
                    x_center_xy[0] + direction[0] * travel,
                    x_center_xy[1] + direction[1] * travel)
                label = "Y acquisition along X beam %s" % (
                    "configured side" if attempt == 0 else "opposite side")
                try:
                    edge = self._scan_line_edge(
                        self.y_beam, x_center_xy, target_xy, z, speed, gcmd,
                        label, "Y_SWEEP_TRAVEL")
                    break
                except self.printer.command_error as e:
                    # A missed beam may be on the other side. Hardware and
                    # motion errors are not recoverable by reversing direction.
                    if not _is_missing_trigger(e):
                        raise
                    errors.append(str(e))
                    gcmd.respond_info(
                        "TCP: %s did not trigger; trying opposite Y direction"
                        % (label,))
            else:
                raise self.printer.command_error(
                    "No trigger on %s during bidirectional Y acquisition "
                    "along the centered X beam from X%.6f Y%.6f at Z%.6f "
                    "with Y_SWEEP_TRAVEL %.6f. "
                    "Last errors: %s"
                    % (self.y_beam.name, x_center_xy[0], x_center_xy[1], z,
                       travel, " | ".join(errors)))
        return edge, x_beam_dir

    def _center_beam_at_z(self, beam, line_dir, approximate_xy, z, travel,
                          speed, passes, gcmd, label):
        coord, center_xy = self._scan_beam_center_on_line(
            beam, line_dir, approximate_xy, z, travel, speed, passes, gcmd,
            label)
        self._move_to_xy(center_xy[0], center_xy[1], z, speed)
        gcmd.respond_info(
            "TCP: %s centered at Z%.6f X=%.6f Y=%.6f coord=%.6f"
            % (label, z, center_xy[0], center_xy[1], coord))
        return {'coord': coord, 'xy': center_xy, 'z': z}

    def _center_beam_if_hit(self, beam, line_dir, approximate_xy, z, travel,
                            speed, passes, gcmd, label):
        # A missing trigger is expected once a Z step moves above the needle
        # tip. Other motion errors still abort calibration immediately.
        try:
            return self._center_beam_at_z(
                beam, line_dir, approximate_xy, z, travel, speed, passes,
                gcmd, label)
        except self.printer.command_error as e:
            if _is_missing_trigger(e):
                return None
            raise

    def _refine_beam_tip_from_miss(self, beam, line_dir, last_hit, clear_z,
                                   tolerance, xy_travel, xy_speed, z_speed,
                                   passes, gcmd, label):
        # Binary-search between the last beam hit and first clear Z. Re-center
        # at every midpoint so a bent needle cannot escape the local XY scan.
        hit = last_hit
        miss_z = clear_z
        while abs(miss_z - hit['z']) > tolerance:
            test_z = 0.5 * (hit['z'] + miss_z)
            self._manual_move([hit['xy'][0], hit['xy'][1], test_z], z_speed)
            centered = self._center_beam_if_hit(
                beam, line_dir, hit['xy'], test_z, xy_travel, xy_speed,
                passes, gcmd, label)
            if centered is None:
                miss_z = test_z
                gcmd.respond_info(
                    "TCP: %s half-step Z%.6f -> no beam hit"
                    % (label, test_z))
            else:
                hit = centered
                gcmd.respond_info(
                    "TCP: %s half-step Z%.6f -> hit at X%.6f Y%.6f"
                    % (label, test_z, hit['xy'][0], hit['xy'][1]))

        tip_z = 0.5 * (hit['z'] + miss_z)
        gcmd.respond_info(
            "TCP: %s tip edge last-hit Z%.6f first-clear Z%.6f -> Z%.6f"
            % (label, hit['z'], miss_z, tip_z))
        return hit, tip_z, miss_z

    def _track_beam_tip_from_center(self, beam, line_dir, first_hit, travel,
                                    step, tolerance, xy_travel, xy_speed,
                                    z_speed, passes, gcmd, label):
        # Bent needles can drift in XY as Z changes. Instead of moving
        # vertically at one fixed XY, every Z step is followed by a fresh local
        # beam-centering sweep around the previous center point.
        last_hit = first_hit
        max_z = first_hit['z'] + travel
        while last_hit['z'] < max_z - TIP_SEARCH_EPSILON:
            test_z = min(last_hit['z'] + step, max_z)
            self._manual_move(
                [last_hit['xy'][0], last_hit['xy'][1], test_z], z_speed)
            state = "PRESSED" if self._query_beam(beam) else "clear"
            gcmd.respond_info(
                "TCP: %s Z step to Z%.6f at previous center -> %s; "
                "sweeping to re-center"
                % (label, test_z, state))
            centered = self._center_beam_if_hit(
                beam, line_dir, last_hit['xy'], test_z, xy_travel, xy_speed,
                passes, gcmd, label)
            if centered is not None:
                last_hit = centered
                continue

            gcmd.respond_info(
                "TCP: %s no beam hit at Z%.6f; refining downward from "
                "last hit Z%.6f"
                % (label, test_z, last_hit['z']))
            refined_hit, tip_z, clear_z = self._refine_beam_tip_from_miss(
                beam, line_dir, last_hit, test_z, tolerance, xy_travel,
                xy_speed, z_speed, passes, gcmd, label)
            return {
                'coord': refined_hit['coord'],
                'xy': refined_hit['xy'],
                'last_hit_z': refined_hit['z'],
                'clear_z': clear_z,
                'tip_z': tip_z,
            }

        raise self.printer.command_error(
            "%s was still found through Z%.6f. Increase Z_TRAVEL or start "
            "lower so the beam-following pass can exceed the needle tip."
            % (beam.name, max_z))

    def _verify_cross_center(self, gcmd):
        # Query one input after the other at the same stationary position. This
        # avoids simultaneous endstop monitoring while proving both beams are
        # disrupted at the calculated intersection.
        x_pressed = self._query_beam(self.x_beam)
        y_pressed = self._query_beam(self.y_beam)
        x_state = "PRESSED" if x_pressed else "clear"
        y_state = "PRESSED" if y_pressed else "clear"
        gcmd.respond_info(
            "TCP: stationary cross-center check X=%s Y=%s"
            % (x_state, y_state))
        if not (x_pressed and y_pressed):
            pos = self.toolhead.get_position()
            raise self.printer.command_error(
                "TCP cross-center verification failed at X%.6f Y%.6f "
                "Z%.6f: X=%s Y=%s. Both beams must be PRESSED without "
                "movement; check beam normals and scan travel settings."
                % (pos[0], pos[1], pos[2], x_state, y_state))

    def _save_float(self, name, value):
        # Save through Klipper's existing SAVE_VARIABLE object instead of
        # writing the variable file directly. This keeps parsing/reload behavior
        # identical to the standard SAVE_VARIABLE command.
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=%.9f" % (name, value))

    def _save_bool(self, name, value):
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=%s"
            % (name, "True" if value else "False"))

    def _get_saved_variables(self):
        save_variables = self.printer.lookup_object('save_variables', None)
        if save_variables is None:
            return {}
        return dict(save_variables.allVariables)

    def _get_bltouch_dock_state(self):
        # Klipper's [bltouch] object knows the probe pin/endstop state, but it
        # does not know whether this detachable probe is physically loaded or
        # parked in the dock. The LOAD_BLTOUCH and PARK_BLTOUCH macros maintain
        # that dock state in save_variables for this safety check.
        svv = self._get_saved_variables()
        state = str(svv.get('bltouch_state', 'unknown')).lower()
        parked_value = svv.get('bltouch_parked', None)
        parked = parked_value is True
        return state, parked

    def _require_bltouch_parked(self):
        if not self.require_bltouch_parked:
            return
        state, parked = self._get_bltouch_dock_state()
        if state == 'parked' and parked:
            return
        raise self.printer.command_error(
            "TCPCALIBRATE blocked: BLTouch saved dock state is "
            "state=%s parked=%s. Run PARK_BLTOUCH first; TCP calibration is "
            "only allowed when the BLTouch is physically parked."
            % (state, parked))

    def _require_tcp_power_on(self):
        # The TCP sensor power is controlled by the TCPON / TCPOFF macros.
        # Keep this guard at the save_variables level so the calibration module
        # obeys the same user-facing state that the macros maintain.
        svv = self._get_saved_variables()
        power_on = svv.get('tcp_power_on', False)
        if power_on is True:
            return
        raise self.printer.command_error(
            "TCPCALIBRATE blocked: TCP sensor output is saved as off "
            "(tcp_power_on=%s). Run TCPON or TCPSTART before calibration."
            % (power_on,))

    def _require_current_tcp_calibration(self):
        svv = self._get_saved_variables()
        try:
            saved_version = int(float(svv.get('tcp_coordinate_version', 0)))
        except (TypeError, ValueError):
            saved_version = 0
        if (svv.get('tcp_ready', False) is True
                and saved_version == TCP_COORDINATE_VERSION):
            return svv
        raise self.printer.command_error(
            "Saved TCP offsets are not valid for coordinate version %d "
            "(tcp_ready=%s, saved version=%s). Run TCPSTART/TCPCALIBRATE "
            "again before using TCP-corrected motion."
            % (TCP_COORDINATE_VERSION, svv.get('tcp_ready', False),
               saved_version))

    cmd_TCPCALIBRATE_help = (
        "Continuously calibrate needle TCP using the optical cross")
    def cmd_TCPCALIBRATE(self, gcmd):
        # Public command. X/Y/Z are the expected final tip/cross position used
        # for offset calculation. The current XY position is the intentional
        # clear start side of the cross. HEIGHT is the low Z where the needle
        # must still cross the X beam before the upward tip search.
        self._require_bltouch_parked()
        self._require_tcp_power_on()
        self._require_homed()
        # A failed run must not leave a previous calibration marked ready.
        self._save_bool('tcp_ready', False)
        expected_x = gcmd.get_float('X')
        expected_y = gcmd.get_float('Y')
        expected_z = gcmd.get_float('Z')
        height = gcmd.get_float('HEIGHT', expected_z)
        params = gcmd.get_command_parameters()
        if 'RADIUS' in params:
            xy_travel = gcmd.get_float('RADIUS', above=0.)
        else:
            xy_travel = gcmd.get_float(
                'XY_TRAVEL', self.default_xy_travel, above=0.)
        if 'PASSES' in params:
            xy_passes = gcmd.get_int('PASSES', minval=1)
        else:
            xy_passes = gcmd.get_int(
                'XY_PASSES', self.default_xy_passes, minval=1)
        x_sweep_travel = gcmd.get_float(
            'X_SWEEP_TRAVEL', self.default_x_sweep_travel, above=0.)
        y_sweep_travel = gcmd.get_float(
            'Y_SWEEP_TRAVEL', self.default_y_sweep_travel, above=0.)
        x_direction = _direction_sign(
            gcmd.get_float('X_DIRECTION', self.default_x_direction),
            'X_DIRECTION', gcmd.error)
        y_direction = _direction_sign(
            gcmd.get_float('Y_DIRECTION', self.default_y_direction),
            'Y_DIRECTION', gcmd.error)
        speed = gcmd.get_float('SPEED', self.default_speed, above=0.)
        z_speed = gcmd.get_float('Z_SPEED', self.default_z_speed, above=0.)
        z_travel = gcmd.get_float('Z_TRAVEL', self.default_z_travel, above=0.)
        z_step = gcmd.get_float('Z_STEP', self.default_z_step, above=0.)
        z_tolerance = gcmd.get_float(
            'Z_TOLERANCE', self.default_z_tolerance, above=0.)

        current = self.toolhead.get_position()
        self._manual_move([current[0], current[1], height], z_speed)
        gcmd.respond_info(
            "TCP: start-right XY acquisition. start X=%.6f Y=%.6f, expected "
            "cross X=%.6f Y=%.6f, HEIGHT=%.6f, X_DIRECTION=%.0f, "
            "Y_DIRECTION=%.0f, "
            "X_SWEEP_TRAVEL=%.6f, Y_SWEEP_TRAVEL=%.6f, "
            "Z_TRAVEL=%.6f, Z_STEP=%.6f, Z_TOLERANCE=%.6f, "
            "XY_TRAVEL=%.6f, passes=%d, speed=%.3f"
            % (current[0], current[1], expected_x, expected_y, height,
               x_direction, y_direction, x_sweep_travel, y_sweep_travel,
               z_travel, z_step, z_tolerance, xy_travel, xy_passes, speed))

        # Phase 1: acquire X, then use orthogonal diagonal sweeps to follow the
        # needle upward until the X beam finds the physical tip edge.
        x_edge = self._acquire_x_beam_from_current_x(
            height, x_direction, x_sweep_travel, speed, gcmd)
        gcmd.respond_info(
            "TCP: X sweep hit %s at X=%.6f Y=%.6f"
            % (self.x_beam.name, x_edge[0], x_edge[1]))

        x_first = self._center_beam_at_z(
            self.x_beam, self.x_normal, (x_edge[0], x_edge[1]),
            height, xy_travel, speed, xy_passes, gcmd,
            "X-beam initial centering")
        x_tip = self._track_beam_tip_from_center(
            self.x_beam, self.x_normal, x_first, z_travel, z_step,
            z_tolerance, xy_travel, speed, z_speed, xy_passes, gcmd,
            "X-beam tip tracking")

        # Phase 2: move two millimeters below the measured tip and remeasure X
        # there. X and Y must be centered in this exact common Z plane.
        tip_z = x_tip['tip_z']
        final_z = tip_z - FINAL_CENTER_Z_DROP
        current_z = self.toolhead.get_position()[2]
        self._move_to_xy(x_tip['xy'][0], x_tip['xy'][1], current_z, speed)
        self._manual_move(
            [x_tip['xy'][0], x_tip['xy'][1], final_z], z_speed)
        x_final = self._center_beam_at_z(
            self.x_beam, self.x_normal, x_tip['xy'], final_z, xy_travel,
            speed, xy_passes, gcmd, "X-beam final-plane centering")

        # Phase 3: stay on the centered X beam while crossing Y. Bidirectional
        # Y edges give its center without changing the measured X coordinate.
        y_edge, x_beam_dir = self._acquire_y_beam_along_x_beam(
            x_final['xy'], final_z, y_direction, y_sweep_travel, speed, gcmd)
        gcmd.respond_info(
            "TCP: diagonal Y sweep hit %s at X=%.6f Y=%.6f"
            % (self.y_beam.name, y_edge[0], y_edge[1]))
        y_final = self._center_beam_at_z(
            self.y_beam, x_beam_dir, (y_edge[0], y_edge[1]), final_z,
            xy_travel, speed, xy_passes, gcmd,
            "Y-beam final-plane centering")

        # Phase 4: solve the same-plane beam intersection, move there once, and
        # query X then Y without moving before accepting the calibration.
        tip_x, tip_y = self._xy_from_beam_coords(
            x_final['coord'], y_final['coord'])
        self._move_to_xy(tip_x, tip_y, final_z, speed)
        self._verify_cross_center(gcmd)

        offset_x = tip_x - expected_x
        offset_y = tip_y - expected_y
        offset_z = tip_z - expected_z
        gcmd.respond_info(
            "TCP: solved same-plane XY centers Xcoord=%.6f "
            "Ycoord=%.6f -> X=%.6f Y=%.6f offsets X=%.6f Y=%.6f"
            % (x_final['coord'], y_final['coord'], tip_x, tip_y, offset_x,
               offset_y))
        gcmd.respond_info(
            "TCP: tip edge Z=%.6f; verified final center Z=%.6f"
            % (tip_z, final_z))

        self.last_result = {
            'tip_x': tip_x, 'tip_y': tip_y, 'tip_z': tip_z,
            'final_x': tip_x, 'final_y': tip_y, 'final_z': final_z,
            'offset_x': offset_x, 'offset_y': offset_y, 'offset_z': offset_z,
            'expected_x': expected_x, 'expected_y': expected_y,
            'expected_z': expected_z,
            'x_beam_coord': x_final['coord'],
            'y_beam_coord': y_final['coord'],
            'x_tip_last_hit_z': x_tip['last_hit_z'],
            'x_tip_clear_z': x_tip['clear_z'],
            'cross_center_verified': True,
        }
        # Only values used by macros survive restart; edge diagnostics remain
        # available through get_status() for the current Klipper session.
        for name in PERSISTED_RESULT_NAMES:
            self._save_float('tcp_' + name, self.last_result[name])
        self._save_float('tcp_coordinate_version', TCP_COORDINATE_VERSION)
        self._save_bool('tcp_ready', True)
        gcmd.respond_info(
            "TCP: done. Tip X=%.6f Y=%.6f Z=%.6f offsets X=%.6f Y=%.6f "
            "Z=%.6f" % (
                tip_x, tip_y, tip_z, offset_x, offset_y, offset_z))

    cmd_TCPQUERYBEAMS_help = "Report current TCP optical beam states"
    def cmd_TCPQUERYBEAMS(self, gcmd):
        self._lookup_runtime_objects()
        x_state = "PRESSED" if self._query_beam(self.x_beam) else "clear"
        y_state = "PRESSED" if self._query_beam(self.y_beam) else "clear"
        gcmd.respond_info(
            "TCP beams: X=%s Y=%s (PRESSED means beam disrupted)"
            % (x_state, y_state))

    cmd_TCPQUERYBLTOUCH_help = "Report saved BLTouch dock state for TCP safety"
    def cmd_TCPQUERYBLTOUCH(self, gcmd):
        state, parked = self._get_bltouch_dock_state()
        guard = "enabled" if self.require_bltouch_parked else "disabled"
        gcmd.respond_info(
            "TCP BLTouch safety: state=%s parked=%s guard=%s"
            % (state, parked, guard))

    cmd_TCPSHOWOFFSETS_help = "Report saved TCP tip coordinates and offsets"
    def cmd_TCPSHOWOFFSETS(self, gcmd):
        svv = self._get_saved_variables()
        gcmd.respond_info(
            "TCP saved: version=%s ready=%s tip X=%s Y=%s Z=%s offsets "
            "X=%s Y=%s Z=%s"
            % (svv.get('tcp_coordinate_version', 'unset'),
               svv.get('tcp_ready', False),
               svv.get('tcp_tip_x', 'unset'),
               svv.get('tcp_tip_y', 'unset'),
               svv.get('tcp_tip_z', 'unset'),
               svv.get('tcp_offset_x', 'unset'),
               svv.get('tcp_offset_y', 'unset'),
               svv.get('tcp_offset_z', 'unset')))

    cmd_TCPMOVEWITHOFFSET_help = (
        "Move to a nominal XYZ plus saved TCP offsets. Args: X Y Z [F]")
    def cmd_TCPMOVEWITHOFFSET(self, gcmd):
        self._require_homed()
        svv = self._require_current_tcp_calibration()
        x = gcmd.get_float('X') + float(svv.get('tcp_offset_x', 0.0))
        y = gcmd.get_float('Y') + float(svv.get('tcp_offset_y', 0.0))
        z = gcmd.get_float('Z') + float(svv.get('tcp_offset_z', 0.0))
        speed = gcmd.get_float('F', 600.0, above=0.) / 60.0
        self._manual_move([x, y, z], speed)
        gcmd.respond_info(
            "TCP move: corrected X=%.6f Y=%.6f Z=%.6f" % (x, y, z))

    def get_status(self, eventtime):
        status = dict(self.last_result)
        state, parked = self._get_bltouch_dock_state()
        status['bltouch_state'] = state
        status['bltouch_parked'] = parked
        status['require_bltouch_parked'] = self.require_bltouch_parked
        status['tcp_power_on'] = (
            self._get_saved_variables().get('tcp_power_on', False) is True)
        status['coordinate_version'] = TCP_COORDINATE_VERSION
        return status


def load_config(config):
    return TCPCalibration(config)
