# OpenSpotter Control Architecture

This document describes the deployable application architecture in the current
tree. It is the boundary guide for changes to core services, pattern plugins,
the desktop shell, generation, and machine control. See
[PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) for an external plugin example
and [VERSIONING.md](VERSIONING.md) for release and schema versions.

## Architecture at a glance

```text
launchers
  -> Tk desktop shell and controllers
       -> application plugin composition
            -> validated built-in and installed pattern plugins
                 -> editors, numeric plans, previews, and runtime snapshots
       -> shared core services
            -> schema/forms, storage, domain, canvas, workflow, G-code lifecycle
       -> workflow renderer
            -> atomic G-code artifact + versioned JSON sidecar
       -> optional machine controller
            -> background Moonraker runtime -> Klipper
```

Saved-file generation stops before the machine boundary and does not require a
printer connection. Direct execution uses the same generation behavior, then
adds artifact validation, operator confirmation, upload, a fresh machine
preflight, and a separate start request.

## Package map

| Location | Responsibility |
| --- | --- |
| `app/core/plugins.py` | Minimal pattern-plugin contract, manifest validation, deterministic discovery, compatibility checks, and duplicate protection. |
| `app/core/application_patterns.py` | Rich desktop-workspace contract, immutable runtime recipe/context models, and shared strict direct-run validators. |
| `app/core/workflow.py` | Typed core/plugin workflow contributions and deterministic conflict-checked aggregation. |
| `app/core/workflow_preview.py` | Plugin-neutral representative event context, common refill/rinse preview calculations, and optional preview-hook dispatch. |
| `app/core/schema.py` | Declarative `Field` definitions, presentation hints, and strict/permissive input coercion. |
| `app/core/ui/forms.py` | Schema-driven Tk entry/combobox and tab construction shared by core screens and plugin editors. |
| `app/core/configuration.py` | Typed field collection plus editable JSON defaults and state persistence. |
| `app/core/storage.py` | Atomic UTF-8 text and JSON replacement. |
| `app/core/domain.py` | Pattern-independent liquid-handling values such as containers and volume conversion. |
| `app/core/geometry.py` | Pattern-independent machine-coordinate geometry such as acceptance bounds. |
| `app/core/gcode/` | Shared workflow-event lifecycle and schema-versioned generation sidecars. |
| `app/core/canvas/` | Renderer-neutral preview context/style, primitives, bounds, and the optional `CanvasPreviewProvider` capability. |
| `app/plugins/grid/` | Grid manifest, fields, geometry, editor, planning, generation, runtime capture, canvas preview, and workflow metadata/preview. |
| `app/plugins/spiral/` | Spiral manifest, fields, editor, planning, generation, runtime capture, canvas preview, and workflow metadata/preview. |
| `app/plugin_runtime.py` | Application composition: discovers plugins and selects those satisfying the desktop contract. |
| `app/gcode_workflow.py` | Safe expression evaluation, workflow validation, template rendering, and the runtime workflow engine. |
| `app/gcode_shared.py` | Desktop generation adapter for common GUI values, paths, and workflow-engine construction. |
| `app/runtime_job.py` | Generic detached plugin snapshots, shared work/artifact limits, hashing, line indexing, and content-addressed runtime artifacts. |
| `app/machine/` | Immutable Moonraker settings/state/events and the background HTTP/WebSocket runtime. |
| `app/machine_controller.py` | Tk-safe direct-run orchestration, preflight, upload/start, and safety interlocks. |
| `app/paths.py` | Immutable resource discovery, writable runtime layout, migration, and first-run default seeding. |

`app/gui_v3.py`, `app/canvas_drawer.py`, `app/gcode_editor.py`, and the window
modules are application-shell code. They may use core and plugin contracts;
core must not import the shell or a concrete pattern plugin.

## Dependency rules

Use these rules for new work:

1. `app/core` owns reusable contracts and services. It must never select or
   import `grid`, `spiral`, another concrete pattern, a shell/controller
   module, or a legacy facade.
2. Pattern packages depend inward on `app/core`. Pure fields, geometry, and
   planning must not import Tkinter, Moonraker, or machine controllers.
3. Non-UI core packages remain Tk-free. `app/core/ui` is the deliberate
   exception for reusable presentation adapters; it must not own planning or
   machine behavior.
4. A plugin editor may depend on Tkinter, `app/core/ui`, and shared theme
   helpers, but it must adapt UI values to the plugin's typed model at its
   boundary.
5. The application shell discovers plugins through `app/plugin_runtime.py` and
   structural protocols. New shell code should not add another
   `if plugin_id == "grid"` dispatch path.
6. Pattern planning returns finite numeric/boolean/string records. It does not
   return G-code, Klipper macros, HTTP requests, or other machine commands.
7. Python owns physical sequencing and numeric state. Machine-command text is
   rendered only from the validated workflow document.
8. Plugins do not import or call `app.machine`, `machine_controller.py`, or
   Moonraker. Generation produces an artifact; the controller decides whether
   and when that artifact may reach a machine.
9. All editable JSON and generated artifacts use atomic storage helpers.
   Package resources are read-only seeds, never writable application state.
10. Cross-boundary values use declared schemas or immutable data objects rather
   than arbitrary GUI objects or module globals.

`tests/test_architecture_boundaries.py` statically enforces the most important
rules: core cannot import concrete patterns, shell modules, or legacy facades;
pure plugin layers depend inward; and legacy facades remain export-only.
Built-in editor/generation/runtime adapters may use application presentation,
logging, and orchestration helpers, but numeric planning stays below them.

## Plugin contracts and lifecycle

### 1. Discovery

`app.plugins.discover_plugins()` asks the process-wide `PluginRegistry` to:

- scan immediate built-in packages under `app.plugins` in alphabetical order;
- call each package's zero-argument `register()` factory;
- load installed `openspotter.patterns` entry points in deterministic order;
- validate each implementation once; and
- reject duplicate plugin IDs without replacing the first registration.

Application discovery logs a broken optional plugin and continues. Direct
registry use raises unless the caller supplies an error handler. Discovery is
idempotent for a successfully loaded source.

### 2. Minimal validation

Every registered plugin has:

- a valid `PluginManifest`;
- an exact `api_version` match with `app.core.plugins.API_VERSION`;
- a stable lowercase ID;
- a callable `plan(context)` method; and
- an optional legacy `name` equal to the manifest ID when it is present.

The minimal contract is enough for headless discovery and numeric planning. It
does not create a desktop tab by itself.

### 3. Desktop selection

`app.plugin_runtime.application_plugins()` keeps registered objects that
structurally satisfy `ApplicationPatternPlugin`. The richer contract adds:

- `WorkspaceSpec` metadata and live instance lookup;
- indexed default-config resolution;
- editor creation;
- canonical editor serialization and restoration;
- structural profile validation;
- atomic default persistence;
- saved-file generation dispatch;
- strict detached direct-run recipe capture;
- worker-safe runtime generation;
- workflow-preview field groups; and
- indexed visual-binding field groups.

Grid and spiral satisfy this contract. Their field schemas live inside their
own packages, while `app/input_configs.py` remains a compatibility export for
older callers.

### 4. Workflow metadata

Core and built-in plugins contribute typed field groups, triggers, variable
scopes, derived variables, context defaults, and required custom variables.
`app/core/workflow.py` aggregates them in explicit order and rejects ownership
conflicts. `app/gcode_workflow.py` consumes the aggregate while preserving its
established compatibility constants.

A trigger contribution declares an event name and its available data. It does
not contain a machine command. The operator-editable
`config/config_gcode_workflow.json` remains the source of command templates.

Representative event previews are also plugin-driven. Optional
`WorkflowPreviewPlugin` implementations claim their own
`workflow_preview_triggers` and enrich a detached `WorkflowPreviewSample`.
Core owns common rinse behavior, refill arithmetic, container selection, and
conflict detection. `app/gcode_editor.py` dispatches discovered application
plugins without knowing grid or spiral event semantics.

### 5. Planning and generation

The normal generation path is:

```text
editor values
  -> plugin serialization/typed collection
  -> plugin.plan(context): numeric records
  -> plugin event planner: named events plus numeric overrides
  -> shared G-code lifecycle: start, refill, empty/rinse, finish
  -> WorkflowEngine: validated templates become command text
  -> atomic G-code output
  -> schema-version 3 settings sidecar
```

`app/gcode_generation.py` already discovers desktop-capable plugins and calls
`instance_map()` and `generate()` for every non-empty plugin. Output suffixes
come from the plugin ID.

Direct execution uses a second, detached route:

```text
Tk thread
  -> plugin.capture_runtime_recipes(...)
  -> immutable PatternRecipeSnapshot records + estimated work
worker
  -> plugin.generate_runtime(RuntimeGenerationContext, recipes, path)
  -> generic size/hash/line-index artifact processing
Tk thread
  -> generic manifest-derived confirmation and artifact preflight
  -> upload with print=false -> fresh preflight -> separate start RPC
```

Core validates global values, plugin IDs, recipe types, total estimated work,
and artifact size. Each plugin strictly captures its own fields and owns its
pattern-specific limits. The controller uses manifest metadata rather than
pattern branches when it describes the pending job.

### 6. Canvas and editor consumers

`WorkspaceValueGroup` exposes live plugin fields in two forms:

- unindexed namespaces for workflow-editor preview values; and
- stable indexed namespaces for visual-object bindings.

Canvas rendering is an optional capability. A plugin satisfying
`CanvasPreviewProvider` receives a `CanvasPreviewContext` containing detached,
top-level read-only global values, the config directory, workflow source, and
a shell-owned `CanvasPreviewStyle`. It returns a `CanvasPreview` containing
markers, polylines, lines, hidden safety points, warnings, and detached
top-level read-only metadata.

Every primitive has a `z_index` and `safety_relevant` flag. The shell:

- combines all provider results without knowing plugin IDs;
- uses every primitive for fit-to-content;
- uses only safety-relevant primitives plus explicit `safety_points` for the
  acceptance warning;
- renders lower `z_index` values first and higher values above them; and
- isolates a failed or malformed provider so other preview layers still draw.

Plugins that do not implement `CanvasPreviewProvider` remain valid desktop and
direct-run plugins; they simply contribute no live pattern geometry.

## Current generic-routing coverage

The application routes pattern behavior through these contracts:

| Area | Current status |
| --- | --- |
| Built-in and installed plugin discovery | Generic and registry-driven. |
| Manifest/API validation and duplicate handling | Generic. |
| Numeric `plan(context)` dispatch | Generic contract. |
| Workflow metadata aggregation | Generic for plugins exposing a valid `workflow_contribution`. |
| Top-level saved-file generation dispatch | Generic for full desktop plugins. |
| Main-window workspaces, add/remove actions, and count restoration | Generic for full desktop plugins; grid/spiral wrapper methods remain for compatibility. |
| Editor/default/field hooks and visual-binding value groups | Generic for full desktop plugins. |
| Profile serialization, validation, and restoration | Generic through schema-version 3 `patterns` entries; legacy built-in arrays remain accepted. |
| Renderer-neutral canvas preview | Generic and optional through `CanvasPreviewProvider`; the shell owns drawing, fit, safety filtering, and z-order. |
| Representative workflow-event preview | Generic and optional through `WorkflowPreviewPlugin`, with common refill/rinse behavior in core. |
| Direct-run snapshot and worker generation | Generic through required `capture_runtime_recipes()` and `generate_runtime()` application-plugin hooks. |
| Machine confirmation, artifact preflight, upload, and start | Generic and manifest/artifact-driven. |
| External plugin config seeding | Not automatic; `PACKAGED_CONFIG_FILES` seeds application-owned defaults only. |

Therefore, an installed minimal plugin can be discovered and used headlessly,
while a full desktop plugin can participate in workspace editing, saved
profiles, state restoration, workflow metadata, visual-binding values, and
saved-file/direct-run generation. It can opt into canvas geometry and detailed
workflow-event previews through separate structural capabilities. A new
pattern does not require a parallel shell, canvas, controller, or runtime-job
branch.

## Configuration and runtime boundaries

`app/paths.py` separates application resources from operator-owned data:

- `resource_dir` contains packaged `config/` seeds and `assets/`;
- `runtime_dir/config` contains editable defaults, workflow, visual objects,
  state, and local Moonraker settings;
- `runtime_dir/output/gcodes` contains generated artifacts; and
- `runtime_dir/logs` contains rotating application logs.

The runtime mode is selected by `OPENSPOTTER_MODE` (`auto`, `source`,
`portable`, or `user`). `OPENSPOTTER_HOME` selects an explicit writable root,
`OPENSPOTTER_MIGRATE_FROM` performs first-run config migration, and
`OPENSPOTTER_RESOURCE_ROOT` is an advanced resource override.

Source checkouts retain local paths. Wheels and frozen builds default to
per-user writable storage. Existing runtime files always win over packaged
seeds. Local `config_moonraker.json`, logs, and generated artifacts are not
package resources.

Source and wheel metadata requires Python 3.8 or newer; CI exercises Python 3.8
and 3.12 on Windows and Ubuntu. Frozen builds bundle their Python interpreter
and must be built/tested separately for each target operating-system family.

The active workflow follows the same separation.
`gcode_workflow.DEFAULT_WORKFLOW_PATH` points at the writable runtime
`WORKFLOW_CONFIG`; `SHIPPED_WORKFLOW_PATH` points at the immutable resource
seed. `WorkflowEngine` falls back to the shipped seed only when the runtime
workflow file is absent.

Configuration versions are independent:

- generation profile schema `3`;
- workspace-state schema `2`;
- G-code workflow schema `1`;
- visual-object schema `2`;
- Moonraker connection settings schema `1`;
- plugin API `1`; and
- firmware/TCP contracts documented in [VERSIONING.md](VERSIONING.md).

Do not couple a plugin release to a silent profile, workflow, or firmware
schema change.

Generation schema `3` stores a generic `patterns` array. Each entry identifies
the `plugin_id`, records the `plugin_version`, and contains that plugin's
canonical `recipes`. Grid and spiral generators also retain
`grid_settings`/`spiral_settings` arrays so schema-version 2 consumers can
migrate without losing built-in data.

Workspace-state schema `2` stores counts under a generic `patterns` mapping
and retains legacy per-plugin count keys. The persisted global key
`max_grid_count` also predates plugins: its operator-facing meaning is
**Maximum Pattern Count**, applied to each registered pattern workspace.

## Machine boundary

The machine subsystem is deliberately downstream of generation:

- `MoonrakerRuntime` owns one daemon thread and asyncio loop;
- callers receive futures and immutable state snapshots;
- runtime callbacks publish bounded local events instead of touching Tk;
- `TkEventBridge` drains those events on the UI thread;
- the selected plugin captures immutable recipes on the Tk thread;
- the selected plugin generates from a detached `RuntimeGenerationContext` in
  a worker, without accessing widgets;
- the controller confirms the manifest display name, recipe count, workflow
  hash, artifact hash, size, line count, and destination generically;
- upload uses `print=false`; start is a separate, freshly preflighted RPC; and
- an uncertain sent-command outcome is never treated as a definite failure.

Pattern plugins cannot weaken these interlocks. A new pattern must generate the
same reviewable artifact boundary, provide a conservative `estimated_work`,
and use the existing controller path for direct machine execution.

## Legacy compatibility shims

The plugin split preserves old imports while callers migrate:

- `app/grid.py` -> `app.plugins.grid.editor` plus
  `app.core.ui.forms.create_labels`;
- `app/spiral_grid.py` -> `app.plugins.spiral.editor`;
- `app/grid_gcode.py` -> `app.plugins.grid.generation`;
- `app/spiral_gcode.py` -> `app.plugins.spiral.generation`;
- `app/gcode_planner.py` -> core lifecycle plus grid/spiral planners;
- `app/input_configs.py` -> core `Field`, global fields, and plugin fields;
- `app/SpotterFunctions.py` -> core configuration/domain/schema/profile helpers
  plus grid geometry; and
- `app/plugins/__init__.py` -> the core registry through the historical
  `discover_plugins()` and `get_plugin()` facade.

These modules are compatibility surfaces, not ownership locations. New code
should import the owning core or plugin module directly. Remove a shim only in
an intentional compatibility release with tests and release notes.

`GenerationSnapshot.grids`/`.spirals` and the built-in GUI wrapper methods are
also compatibility views. Generic code uses `recipes`, plugin IDs, and
`instance_pattern()` instead.

## Adding another core package

Create a core package when behavior is shared by multiple plugins or by both
saved-file and direct-run paths, has a clear data contract, and does not know a
concrete pattern. Keep business/domain packages independent from UI widgets;
reusable Tk-only adapters belong explicitly under `app/core/ui`. Prefer:

```text
app/core/<capability>/
  __init__.py       public exports
  models.py         immutable values/contracts
  service.py        pure or infrastructure-neutral behavior
```

Keep adapters in the shell or plugin package. Add focused tests for the public
contract and at least one integration test at each boundary that consumes it.
