# Continuous optical-cross TCP calibration.
#
# This module uses Klipper's MCU endstop homing path so calibration moves can
# stop on beam transitions without the jitter of macro-level polling.
#
# Important movement model:
#   Klipper's homing/probing stop-on-endstop path operates on one straight move
#   at a time. This module therefore does not trace the old macro's circle.
#   Instead, the needle is deliberately placed to one side of the 45-degree
#   optical cross, then the module performs:
#     1. one pure-X acquisition sweep until either beam is hit,
#     2. a local bidirectional scan to center that first beam,
#     3. a search along that physical 45-degree beam line for the other beam,
#     4. a local bidirectional scan to center the other beam,
#     5. the existing Z height calibration at the measured XY cross.

import math

from . import homing


# Beam normals define the coordinate measured by each beam. They are
# perpendicular to the physical beam lines:
#   physical X beam line: +45 degrees in XY
#   physical Y beam line: -45 degrees in XY
#
# The default values preserve the old macro's 45-degree optical-cross transform:
#   x_beam_coord = (-x + y) / sqrt(2)
#   y_beam_coord = ( x + y) / sqrt(2)
DEFAULT_X_BEAM_NORMAL = (-0.70710678118, 0.70710678118)
DEFAULT_Y_BEAM_NORMAL = (0.70710678118, 0.70710678118)


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
        self.default_cross_search_travel = config.getfloat(
            'cross_search_travel', 10.0, above=0.)
        self.default_x_direction = config.getfloat('x_direction', -1.0)
        if not self.default_x_direction:
            raise config.error("tcp_calibration x_direction can not be zero")
        self.default_x_direction = (
            -1.0 if self.default_x_direction < 0.0 else 1.0)
        self.default_xy_passes = config.getint('xy_passes', 2, minval=1)
        self.default_speed = config.getfloat('speed', 5.0, above=0.)
        self.default_z_speed = config.getfloat('z_speed', 1.0, above=0.)
        self.default_z_travel = config.getfloat('z_travel', 4.0, above=0.)
        self.default_z_passes = config.getint('z_passes', 3, minval=1)
        self.default_z_beam = config.getchoice(
            'z_beam', {'x': 'x', 'y': 'y', 'both': 'both'}, 'both')
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
        length = math.sqrt(x * x + y * y)
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

    def _other_beam(self, beam):
        if beam is self.x_beam:
            return self.y_beam
        return self.x_beam

    def _beam_letter(self, beam):
        if beam is self.x_beam:
            return "X"
        return "Y"

    def _physical_beam_direction(self, beam):
        # The configured values are beam normals, not the physical beam lines.
        # A perpendicular vector gives the actual 45-degree line to follow when
        # travelling along a beam toward the cross intersection.
        nx, ny = self._beam_normal(beam)
        return self._normalize((ny, -nx))

    def _orient_toward(self, direction, start_xy, target_xy):
        # Beam direction has two valid signs. Use the one that points from the
        # current measured beam point toward the expected cross position.
        dx, dy = direction
        vx = target_xy[0] - start_xy[0]
        vy = target_xy[1] - start_xy[1]
        if vx * dx + vy * dy < 0.0:
            return -dx, -dy
        return dx, dy

    def _xy_distance(self, a, b):
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return math.sqrt(dx * dx + dy * dy)

    def _beam_coord(self, normal, pos):
        # Project a toolhead XY point onto a beam normal. A physical beam is
        # modeled as all XY points with the same projected coordinate.
        return normal[0] * pos[0] + normal[1] * pos[1]

    def _beam_distance_along_x(self, beam, start_xy, expected_xy,
                               x_direction):
        normal = self._beam_normal(beam)
        denom = normal[0] * x_direction
        if abs(denom) < 0.000001:
            return None
        expected_coord = self._beam_coord(normal, expected_xy)
        start_coord = self._beam_coord(normal, start_xy)
        distance = (expected_coord - start_coord) / denom
        if distance <= 0.000001:
            return None
        return distance

    def _select_first_sweep_beam(self, start_xy, expected_xy, x_direction,
                                 first_beam_name):
        first_beam_name = first_beam_name.lower()
        if first_beam_name == 'x':
            return self.x_beam, None
        if first_beam_name == 'y':
            return self.y_beam, None
        if first_beam_name != 'auto':
            raise self.printer.command_error(
                "FIRSTBEAM must be X, Y, or AUTO")

        candidates = []
        for beam in (self.x_beam, self.y_beam):
            distance = self._beam_distance_along_x(
                beam, start_xy, expected_xy, x_direction)
            if distance is not None:
                candidates.append((distance, beam))
        if not candidates:
            raise self.printer.command_error(
                "TCPCALIBRATE can not auto-select the first beam: the "
                "expected cross is not ahead of the current start point along "
                "the X sweep. For TCPSTART, pass CALX/CALY for the expected "
                "beam cross, or force FIRSTBEAM=X / FIRSTBEAM=Y.")
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1], candidates[0][0]

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

    def _probe_to(self, beam, target, speed, triggered=True):
        # This is the core continuous-motion call. It performs one straight
        # homing/probing move and lets the MCU stop motion when the beam reaches
        # the requested state:
        #   triggered=True  -> stop when the beam becomes disrupted
        #   triggered=False -> stop when the beam becomes clear
        self._lookup_runtime_objects()
        return self.homing.manual_home(
            self.toolhead, [(beam.mcu_endstop, beam.name)], target, speed,
            probe_pos=True, triggered=triggered, check_triggered=True)

    def _probe_to_any(self, beams, target, speed, description):
        raise self.printer.command_error(
            "Internal TCP calibration error: multi-beam continuous homing is "
            "disabled because the MCU can not arm two trigger groups on the "
            "same XYZ steppers. Use FIRSTBEAM=X/Y or FIRSTBEAM=AUTO.")
        # Klipper's normal manual_home() can watch several endstops, but it
        # reports an error if not every watched endstop triggered. For the first
        # acquisition sweep we intentionally want "stop when either beam hits",
        # so this mirrors HomingMove.homing_move() and returns the earliest
        # beam that triggered.
        self._lookup_runtime_objects()
        endstops = [(beam.mcu_endstop, beam.name) for beam in beams]
        hmove = homing.HomingMove(self.printer, endstops, self.toolhead)
        if not hmove.endstops:
            raise self.printer.command_error(
                "No TCP beam endstops have steppers attached")

        self.printer.send_event("homing:homing_move_begin", hmove)
        self.toolhead.flush_step_generation()
        kin = self.toolhead.get_kinematics()
        kin_spos = {s.get_name(): s.get_commanded_position()
                    for s in kin.get_steppers()}
        hmove.stepper_positions = [
            homing.StepperPosition(s, name)
            for es, name in hmove.endstops
            for s in es.get_steppers()]

        print_time = self.toolhead.get_last_move_time()
        endstop_triggers = []
        for mcu_endstop, name in hmove.endstops:
            rest_time = hmove._calc_endstop_rate(mcu_endstop, target, speed)
            wait = mcu_endstop.home_start(
                print_time, homing.ENDSTOP_SAMPLE_TIME,
                homing.ENDSTOP_SAMPLE_COUNT, rest_time, triggered=True)
            endstop_triggers.append(wait)
        any_endstop_trigger = homing.multi_complete(
            self.printer, endstop_triggers)
        self.toolhead.dwell(homing.HOMING_START_DELAY)

        error = None
        try:
            self.toolhead.drip_move(target, speed, any_endstop_trigger)
        except self.printer.command_error as e:
            error = "Error during %s: %s" % (description, str(e))

        trigger_times = {}
        move_end_print_time = self.toolhead.get_last_move_time()
        for mcu_endstop, name in hmove.endstops:
            try:
                trigger_time = mcu_endstop.home_wait(move_end_print_time)
            except self.printer.command_error as e:
                if error is None:
                    error = "Error during %s on %s: %s" % (
                        description, name, str(e))
                continue
            if trigger_time > 0.0:
                trigger_times[name] = trigger_time

        triggered_name = None
        if trigger_times:
            triggered_name = min(trigger_times, key=trigger_times.get)

        self.toolhead.flush_step_generation()
        for sp in hmove.stepper_positions:
            tt = trigger_times.get(sp.endstop_name, move_end_print_time)
            sp.note_home_end(tt)

        if triggered_name is not None:
            active_positions = [
                sp for sp in hmove.stepper_positions
                if sp.endstop_name == triggered_name]
            halt_steps = {sp.stepper_name: sp.halt_pos - sp.start_pos
                          for sp in active_positions}
            trig_steps = {sp.stepper_name: sp.trig_pos - sp.start_pos
                          for sp in active_positions}
            haltpos = trigpos = hmove.calc_toolhead_pos(kin_spos, trig_steps)
            if trig_steps != halt_steps:
                haltpos = hmove.calc_toolhead_pos(kin_spos, halt_steps)
            self.toolhead.set_position(haltpos)
            for sp in active_positions:
                sp.verify_no_probe_skew(haltpos)
        else:
            trigpos = list(target)
            self.toolhead.set_position(target)

        try:
            self.printer.send_event("homing:homing_move_end", hmove)
        except self.printer.command_error as e:
            if error is None:
                error = str(e)

        if error is not None:
            raise self.printer.command_error(error)
        if triggered_name is None:
            raise self.printer.command_error(
                "No trigger on tcp_beam_x or tcp_beam_y during %s. The "
                "initial sweep only moves in X, so start on the safe side of "
                "the 45-degree cross, increase X_SWEEP_TRAVEL, or verify both "
                "beam pin states with TCPQUERYBEAMS." % (description,))

        for beam in beams:
            if beam.name == triggered_name:
                return beam, trigpos
        raise self.printer.command_error(
            "Internal TCP calibration error: unknown triggered beam %s"
            % (triggered_name,))

    def _move_to_xy(self, x, y, z, speed):
        self._manual_move([x, y, z], speed)

    def _scan_line_edge(self, beam, start_xy, target_xy, z, speed, gcmd,
                        label):
        # Move to a clear start point first. This positioning move is not the
        # measurement; the following _probe_to() line is the monitored move.
        # If the visible crossing happens during this positioning move, increase
        # XY_TRAVEL or adjust the approximate beam point so the monitored
        # start->target line brackets the actual beam edge.
        self._move_to_xy(start_xy[0], start_xy[1], z, speed)
        if self._query_beam(beam):
            raise self.printer.command_error(
                "%s is already triggered at %s scan start. Increase "
                "XY_TRAVEL or move the approximate beam point closer to the "
                "beam center." % (beam.name, label))
        target = list(self.toolhead.get_position())
        target[0] = target_xy[0]
        target[1] = target_xy[1]
        target[2] = z
        gcmd.respond_info(
            "TCP: %s %s straight scan X%.6f Y%.6f -> X%.6f Y%.6f at Z%.6f"
            % (beam.name, label, start_xy[0], start_xy[1],
               target_xy[0], target_xy[1], z))
        try:
            return self._probe_to(beam, target, speed, triggered=True)
        except self.printer.command_error as e:
            raise self.printer.command_error(
                "%s while scanning %s during %s from X%.6f Y%.6f to "
                "X%.6f Y%.6f. "
                "The monitored move is a straight line, not a circle. If the "
                "beam visibly crossed during the previous positioning move, "
                "increase XY_TRAVEL or adjust the approximate point. If it "
                "crossed during this straight scan, run TCPQUERYBEAMS while "
                "manually blocking the beam to verify pin/invert state."
                % (str(e), beam.name, label, start_xy[0], start_xy[1],
                   target_xy[0], target_xy[1]))

    def _scan_beam_center_on_line(self, beam, line_dir, approximate_xy, z,
                                  travel, speed, passes, gcmd, label):
        # Measure one optical beam by crossing it from both sides on a chosen
        # straight line. Averaging the two trigger points estimates the beam
        # center and cancels much of the beam-width / hysteresis error.
        line_dir = self._normalize(line_dir)
        normal = self._beam_normal(beam)
        values = []
        points = []
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
            values.append(beam_coord)
            points.append(center_xy)
            gcmd.respond_info(
                "TCP: %s %s sample %d/%d coords %.6f %.6f -> %.6f"
                % (beam.name, label, sample + 1, passes, coord_a,
                   coord_b, beam_coord))
        avg_coord = sum(values) / len(values)
        avg_point = (sum([p[0] for p in points]) / len(points),
                     sum([p[1] for p in points]) / len(points))
        return avg_coord, avg_point

    def _acquire_first_beam_from_current_x(self, expected_xy, z, x_direction,
                                           travel, speed, first_beam_name,
                                           gcmd):
        # The operator jogs the needle to the chosen safe side of the
        # 45-degree cross. From that exact XY point we move only in X until
        # the selected optical beam trips. Klipper can not safely arm both
        # beam endstops on the same XYZ steppers at once; doing so makes the
        # MCU reject the move with "Can't add signal that is already active".
        pos = self.toolhead.get_position()
        start_xy = (pos[0], pos[1])
        for beam in (self.x_beam, self.y_beam):
            if self._query_beam(beam):
                raise self.printer.command_error(
                    "%s is already triggered before the first X sweep. Jog "
                    "the needle to the clear left/start side of the optical "
                    "cross or verify the beam input with TCPQUERYBEAMS."
                    % (beam.name,))
        first_beam, predicted_distance = self._select_first_sweep_beam(
            start_xy, expected_xy, x_direction, first_beam_name)
        target = list(pos)
        target[0] = pos[0] + x_direction * travel
        target[1] = pos[1]
        target[2] = z
        if predicted_distance is None:
            gcmd.respond_info(
                "TCP: acquisition X sweep watching %s by request from "
                "X%.6f Y%.6f to X%.6f Y%.6f"
                % (first_beam.name, start_xy[0], start_xy[1],
                   target[0], target[1]))
        else:
            gcmd.respond_info(
                "TCP: acquisition X sweep watching %s from X%.6f Y%.6f to "
                "X%.6f Y%.6f; predicted beam distance %.6f"
                % (first_beam.name, start_xy[0], start_xy[1],
                   target[0], target[1], predicted_distance))
            if predicted_distance > travel:
                raise self.printer.command_error(
                    "TCPCALIBRATE predicted %s is %.6f mm away, beyond "
                    "X_SWEEP_TRAVEL %.6f. Increase X_SWEEP_TRAVEL, move the "
                    "start point closer, or check CALX/CALY."
                    % (first_beam.name, predicted_distance, travel))
        try:
            edge = self._probe_to(first_beam, target, speed, triggered=True)
        except self.printer.command_error as e:
            raise self.printer.command_error(
                "%s during initial X acquisition sweep while watching %s. "
                "Only one beam can be watched continuously on this MCU; use "
                "FIRSTBEAM=X/Y if AUTO picked the wrong first beam, or check "
                "TCPQUERYBEAMS and X_SWEEP_TRAVEL."
                % (str(e), first_beam.name))
        return first_beam, edge

    def _search_other_beam_on_first_beam(self, first_beam, first_center_xy,
                                         expected_xy, z, travel, edge_travel,
                                         speed, gcmd):
        # Once the first beam is centered, travel along that physical 45-degree
        # beam line toward the expected cross. Because the two beams are a
        # 45-degree rotated cross, moving along one beam crosses the other beam
        # almost perpendicularly.
        other_beam = self._other_beam(first_beam)
        beam_dir = self._physical_beam_direction(first_beam)
        beam_dir = self._orient_toward(beam_dir, first_center_xy, expected_xy)
        distance_to_expected = self._xy_distance(first_center_xy, expected_xy)
        search_distance = max(travel, distance_to_expected + edge_travel)

        self._move_to_xy(first_center_xy[0], first_center_xy[1], z, speed)
        if self._query_beam(other_beam):
            other_edge = list(self.toolhead.get_position())
            gcmd.respond_info(
                "TCP: %s already triggered while centered on %s beam; using "
                "that point as the approximate second-beam location"
                % (other_beam.name, first_beam.name))
        else:
            target_xy = (first_center_xy[0] + beam_dir[0] * search_distance,
                         first_center_xy[1] + beam_dir[1] * search_distance)
            other_edge = self._scan_line_edge(
                other_beam, first_center_xy, target_xy, z, speed, gcmd,
                "second-beam acquisition")
        return other_beam, other_edge, beam_dir

    def _scan_z_once(self, beam, x, y, height, travel, speed):
        # Z uses the same endstop-stop mechanism, but it watches beam state
        # transitions vertically:
        #   1. If starting inside the beam, move up until clear.
        #   2. Move down until pressed.
        #   3. Move up until clear.
        #   4. Average those down/up edges as the vertical beam center.
        top_z = height + travel
        bottom_z = height - travel
        self._manual_move([x, y, height], speed)

        if self._query_beam(beam):
            target = list(self.toolhead.get_position())
            target[2] = top_z
            self._probe_to(beam, target, speed, triggered=False)

        if self._query_beam(beam):
            raise self.printer.command_error(
                "%s did not clear while moving up. Increase Z_TRAVEL or "
                "check the expected X/Y center." % (beam.name,))

        target = list(self.toolhead.get_position())
        target[2] = bottom_z
        pressed = self._probe_to(beam, target, speed, triggered=True)

        target = list(self.toolhead.get_position())
        target[2] = top_z
        cleared = self._probe_to(beam, target, speed, triggered=False)
        return 0.5 * (pressed[2] + cleared[2]), pressed[2], cleared[2]

    def _scan_z(self, beams, x, y, height, travel, speed, passes, gcmd):
        values = []
        for beam in beams:
            for sample in range(passes):
                z, pressed_z, cleared_z = self._scan_z_once(
                    beam, x, y, height, travel, speed)
                values.append(z)
                gcmd.respond_info(
                    "TCP: %s Z sample %d/%d pressed %.6f clear %.6f -> %.6f"
                    % (beam.name, sample + 1, passes, pressed_z, cleared_z,
                       z))
        return sum(values) / len(values)

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

    cmd_TCPCALIBRATE_help = (
        "Continuously calibrate needle TCP using the optical cross")
    def cmd_TCPCALIBRATE(self, gcmd):
        # Public command. X/Y/Z are the expected final tip/cross position used
        # for offset calculation. The current XY position is the intentional
        # clear start side of the cross. HEIGHT is an absolute Z used for the
        # XY beam scans and as the Z scan center.
        self._require_bltouch_parked()
        self._require_tcp_power_on()
        self._require_homed()
        expected_x = gcmd.get_float('X')
        expected_y = gcmd.get_float('Y')
        expected_z = gcmd.get_float('Z')
        height = gcmd.get_float('HEIGHT', expected_z)
        if 'RADIUS' in gcmd.get_command_parameters():
            xy_travel = gcmd.get_float('RADIUS', above=0.)
        else:
            xy_travel = gcmd.get_float(
                'XY_TRAVEL', self.default_xy_travel, above=0.)
        if 'PASSES' in gcmd.get_command_parameters():
            xy_passes = gcmd.get_int('PASSES', minval=1)
        else:
            xy_passes = gcmd.get_int(
                'XY_PASSES', self.default_xy_passes, minval=1)
        x_sweep_travel = gcmd.get_float(
            'X_SWEEP_TRAVEL', self.default_x_sweep_travel, above=0.)
        cross_search_travel = gcmd.get_float(
            'CROSS_SEARCH_TRAVEL', self.default_cross_search_travel, above=0.)
        x_direction = gcmd.get_float('X_DIRECTION', self.default_x_direction)
        if not x_direction:
            raise gcmd.error("X_DIRECTION can not be zero")
        x_direction = -1.0 if x_direction < 0.0 else 1.0
        speed = gcmd.get_float('SPEED', self.default_speed, above=0.)
        z_speed = gcmd.get_float('Z_SPEED', self.default_z_speed, above=0.)
        z_travel = gcmd.get_float('Z_TRAVEL', self.default_z_travel, above=0.)
        z_passes = gcmd.get_int('Z_PASSES', self.default_z_passes, minval=1)
        cmd_params = gcmd.get_command_parameters()
        first_beam_name = cmd_params.get(
            'FIRST_BEAM', cmd_params.get('FIRSTBEAM', 'AUTO'))
        z_beam_name = gcmd.get('Z_BEAM', self.default_z_beam).lower()
        if z_beam_name == 'x':
            z_beams = [self.x_beam]
        elif z_beam_name == 'y':
            z_beams = [self.y_beam]
        elif z_beam_name == 'both':
            z_beams = [self.x_beam, self.y_beam]
        else:
            raise gcmd.error("Z_BEAM must be X, Y, or BOTH")

        current = self.toolhead.get_position()
        self._manual_move([current[0], current[1], height], z_speed)
        expected_xy = (expected_x, expected_y)
        gcmd.respond_info(
            "TCP: start-left XY acquisition. start X=%.6f Y=%.6f, expected "
            "cross X=%.6f Y=%.6f, HEIGHT=%.6f, X_DIRECTION=%.0f, "
            "FIRSTBEAM=%s, "
            "X_SWEEP_TRAVEL=%.6f, CROSS_SEARCH_TRAVEL=%.6f, "
            "XY_TRAVEL=%.6f, passes=%d, speed=%.3f"
            % (current[0], current[1], expected_x, expected_y, height,
               x_direction, first_beam_name, x_sweep_travel,
               cross_search_travel, xy_travel, xy_passes, speed))

        first_beam, first_edge = self._acquire_first_beam_from_current_x(
            expected_xy, height, x_direction, x_sweep_travel, speed,
            first_beam_name, gcmd)
        gcmd.respond_info(
            "TCP: first X sweep hit %s at X=%.6f Y=%.6f"
            % (first_beam.name, first_edge[0], first_edge[1]))

        first_coord, first_center_xy = self._scan_beam_center_on_line(
            first_beam, (x_direction, 0.0), (first_edge[0], first_edge[1]),
            height, xy_travel, speed, xy_passes, gcmd,
            "first-beam centering")
        gcmd.respond_info(
            "TCP: centered first %s beam at X=%.6f Y=%.6f coord=%.6f"
            % (self._beam_letter(first_beam), first_center_xy[0],
               first_center_xy[1], first_coord))

        other_beam, other_edge, first_beam_dir = (
            self._search_other_beam_on_first_beam(
                first_beam, first_center_xy, expected_xy, height,
                cross_search_travel, xy_travel, speed, gcmd))
        gcmd.respond_info(
            "TCP: second search found %s while following %s beam at X=%.6f "
            "Y=%.6f"
            % (other_beam.name, first_beam.name, other_edge[0],
               other_edge[1]))

        other_coord, other_center_xy = self._scan_beam_center_on_line(
            other_beam, first_beam_dir, (other_edge[0], other_edge[1]),
            height, xy_travel, speed, xy_passes, gcmd,
            "second-beam centering")
        gcmd.respond_info(
            "TCP: centered second %s beam at X=%.6f Y=%.6f coord=%.6f"
            % (self._beam_letter(other_beam), other_center_xy[0],
               other_center_xy[1], other_coord))

        if first_beam is self.x_beam:
            x_coord = first_coord
            y_coord = other_coord
        else:
            x_coord = other_coord
            y_coord = first_coord
        tip_x, tip_y = self._xy_from_beam_coords(x_coord, y_coord)
        offset_x = tip_x - expected_x
        offset_y = tip_y - expected_y

        self._manual_move([tip_x, tip_y, height], speed)
        gcmd.respond_info(
            "TCP: XY center X=%.6f Y=%.6f offsets X=%.6f Y=%.6f"
            % (tip_x, tip_y, offset_x, offset_y))

        gcmd.respond_info(
            "TCP: continuous Z scan from HEIGHT=%.6f travel=%.6f passes=%d "
            "beam=%s speed=%.3f" % (
                height, z_travel, z_passes, z_beam_name, z_speed))
        tip_z = self._scan_z(
            z_beams, tip_x, tip_y, height, z_travel, z_speed, z_passes, gcmd)
        offset_z = tip_z - expected_z

        self.last_result = {
            'tip_x': tip_x, 'tip_y': tip_y, 'tip_z': tip_z,
            'offset_x': offset_x, 'offset_y': offset_y, 'offset_z': offset_z,
            'expected_x': expected_x, 'expected_y': expected_y,
            'expected_z': expected_z,
        }
        self._save_float('tcp_tip_x', tip_x)
        self._save_float('tcp_tip_y', tip_y)
        self._save_float('tcp_tip_z', tip_z)
        self._save_float('tcp_expected_x', expected_x)
        self._save_float('tcp_expected_y', expected_y)
        self._save_float('tcp_expected_z', expected_z)
        self._save_float('tcp_offset_x', offset_x)
        self._save_float('tcp_offset_y', offset_y)
        self._save_float('tcp_offset_z', offset_z)
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
            "TCP saved: tip X=%s Y=%s Z=%s offsets X=%s Y=%s Z=%s"
            % (svv.get('tcp_tip_x', 'unset'),
               svv.get('tcp_tip_y', 'unset'),
               svv.get('tcp_tip_z', 'unset'),
               svv.get('tcp_offset_x', 'unset'),
               svv.get('tcp_offset_y', 'unset'),
               svv.get('tcp_offset_z', 'unset')))

    cmd_TCPMOVEWITHOFFSET_help = (
        "Move to a nominal XYZ plus saved TCP offsets. Args: X Y Z [F]")
    def cmd_TCPMOVEWITHOFFSET(self, gcmd):
        self._require_homed()
        svv = self._get_saved_variables()
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
        return status


def load_config(config):
    return TCPCalibration(config)
