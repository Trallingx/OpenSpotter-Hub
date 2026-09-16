# Project Description

## Purpose

Klipper OpenSource Spotter is a PyQt6 desktop application for drop-on-demand spotting workflows.
It provides UI control for valves and macro execution while integrating with Moonraker/Klipper.

## Scope

- GUI-first operation for machine control and monitoring
- Spotting/canvas workflows and progress feedback
- Live toolhead position display on the spotting canvas
- Config-driven machine connection and behavior
- Extensible architecture for future camera and print logic

## Architecture

- Models: core data structures and state
- Views: PyQt6 panels and canvas widgets
- Controllers: orchestration and interaction logic
- Services: external integrations (Moonraker, camera, logging)
- Utils: shared config, helpers, signal bus

## Current Status

Implemented:
- Main window and panel composition
- Signal bus and event-based communication
- Moonraker connectivity (REST + WebSocket client with subscribed toolhead position updates)
- Moonraker-backed Pi file editor for config/scripts, local Pi-target file upload prompts, Klipper restart, and Moonraker-authorized service actions.
- Core model layer and model tests
- Hardware-only spotting workflow with live progress updates
- Klipper valve firing routes through the provided valve macros, with spotting using the unified `SHOOT` wrapper.
- The provided Klipper snippet preloads Arduino timing through the Pi-side bridge and uses Pi host-MCU GPIO edges for per-spot firing in continuous-motion mode.
- The GUI sends configured connect G-code after Moonraker connects; the current default starts the Arduino valve bridge service.
- Spotting sends a single `SHOOT` command per spot with `X`, `Y`, and `SPEED_MM_S`; the Klipper macro places the `G1` move and Pi-MCU Arduino trigger edge together without adding a hard `M400` stop. Zero pre/post waits leave motion continuous, while configured waits intentionally add timing delay around the shot.
- Spotting now checks X/Y homing before dispatch so invalid motion commands do not get sent to Klipper.
- Spotting start preflight uses cached WebSocket toolhead status instead of repeated blocking REST status queries.
- Spotting dispatch uses a configurable send-ahead window. The first dispatch sends up to `dispatch_window_spots`; after `dispatch_refill_threshold_spots` more spots complete, the controller tops the in-flight queue back up to the window. `dispatch_batch_spots` still limits how many lines are grouped into one Moonraker script request.
- Spotting sequence planning is virtual and row-indexed: large grids expose indexed `Spot` objects on demand instead of storing every spot. Position completion projects only the dispatched, incomplete window, not the full planned path.
- Spotting progress follows WebSocket `motion_report.live_position` samples in Pi-MCU trigger mode because trigger edges are queued with motion; USB fallback follows completed Arduino fire command responses.
- The spotting canvas shows the latest toolhead position as a black X from live gantry position updates.
- Roll-to-roll canvas mode avoids full-Y rendering for large row counts by drawing two anchored rows per active grid and a top-right `current/total` row legend per grid.
- Active Stop and app shutdown are soft stops: they stop local dispatch/refill, unblock a paused spotting worker, and clear pending publisher scripts without requesting Moonraker emergency stop. Already accepted Klipper batches are allowed to drain.
- The background status listener uses the WebSocket status cache when connected and avoids repeated REST polling on the hot path.
- Spotting now aborts immediately on Moonraker/Klippy disconnect so the UI does not hang on a dead command queue.
- Valve config editing now uses per-valve tabs and omits pulse-width fields.
- Standalone valve control bar has been removed; fire actions live inside each valve config tab.
- Machine configuration editing is limited to machine, gantry, Klipper, and valve settings; grid definitions are edited from the main window grid panel.
- Grid valve assignment is now embedded in each grid tab as a dropdown.
- Grid sets can now be emptied completely and rebuilt from zero.
- Grid names are editable per tab and tab labels stay tied to the stored grid name.
- Grid tabs include an Active toggle, and inactive grids are skipped by the spotting sequence.
- Grid changes now trigger a full canvas redraw so active grids remain visible after load or add.
- Grid visuals are layered above the background matrix grid so the active layout stays on top.
- Grid valve selectors only expose active valves.

Temporary TODO:
- Calibration manager and calibration workflow are removed for now to avoid broken imports while that feature is reworked.

In progress / partial:
- End-to-end spotting workflow refinement
- Full camera acquisition and processing
- Broader integration and regression test coverage

## Maintenance Boundary

- [AGENTS.md](AGENTS.md) is the source of truth for Codex and contributor workflow.
- Generated files, caches, virtualenv contents, and runtime logs are not source files.
- Future feature work should extend the closest existing model, controller, service, view, signal, and config pattern before introducing new abstractions.
- Hardware-facing changes should be based on code, config, and log evidence, not assumptions.

## Non-Goals (Current Version)

- Production-ready vision stack
- Fully automatic calibration pipeline
- Cloud backend or remote fleet orchestration

## Success Criteria

- App starts reliably and connects when Moonraker is reachable
- Core user actions are reflected in UI and logs
- Config changes are loaded/saved consistently
- Documentation remains aligned with behavior
