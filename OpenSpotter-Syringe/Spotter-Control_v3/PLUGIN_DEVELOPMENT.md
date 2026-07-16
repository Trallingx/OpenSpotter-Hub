# Pattern Plugin Development

OpenSpotter supports installed pattern plugins through the
`openspotter.patterns` Python entry-point group. This guide covers the current
API, a minimal external planner, and the richer hooks used by the desktop
application.

Read [ARCHITECTURE.md](ARCHITECTURE.md) first. In particular, a discovered
minimal planner is usable through the registry but does not automatically gain
a desktop workspace. A full application plugin can join the generic editor,
state, profile, workflow-metadata, saved-file generation, and direct machine-run
paths. Canvas geometry and detailed workflow-event previews are optional
capabilities.

## Choose the integration level

There are two required structural contracts and two optional capabilities:

1. `PatternPlugin` is the stable minimum: manifest plus
   `plan(context) -> numeric records`.
2. `ApplicationPatternPlugin` adds workspace metadata, fields/editor handling,
   profiles/defaults, saved/runtime generation, workflow field groups, and
   visual bindings.
3. `CanvasPreviewProvider` optionally adds renderer-neutral live geometry.
4. `WorkflowPreviewPlugin` optionally adds realistic representative values for
   plugin-owned workflow events.

Start with the minimal contract. Add desktop hooks only when the planner is
deterministic and its data model is settled.

## Minimal external entry-point plugin

Example package:

```text
openspotter-dots/
  pyproject.toml
  src/
    openspotter_dots/
      __init__.py
      plugin.py
  tests/
    test_plugin.py
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "openspotter-dots"
version = "0.1.0"
requires-python = ">=3.8"
dependencies = ["openspotter-control"]

[project.entry-points."openspotter.patterns"]
dots = "openspotter_dots.plugin:register"

[tool.setuptools.packages.find]
where = ["src"]
```

`src/openspotter_dots/plugin.py`:

```python
import math

from app.core import API_VERSION, PluginManifest


class DotsPlugin:
    manifest = PluginManifest(
        id="dots",
        display_name="Dots",
        version="0.1.0",
        api_version=API_VERSION,
        description="A deterministic line of numeric spot events.",
        capabilities=("numeric-plan",),
    )
    name = manifest.id

    def plan(self, context):
        params = dict(context.get("params", {}))
        count = int(params.get("count", 1))
        x = float(params.get("x", 0.0))
        y = float(params.get("y", 0.0))
        pitch = float(params.get("pitch", 1.0))
        volume_ul = float(params.get("volume_ul", 0.0))

        values = (x, y, pitch, volume_ul)
        if count < 0 or not all(math.isfinite(value) for value in values):
            raise ValueError("Dots parameters must be finite and count non-negative")
        if volume_ul < 0:
            raise ValueError("volume_ul cannot be negative")

        return [
            {
                "index": index,
                "x": x + index * pitch,
                "y": y,
                "dispense_ul": volume_ul,
            }
            for index in range(count)
        ]


def register():
    return DotsPlugin()
```

`src/openspotter_dots/__init__.py` may simply re-export `DotsPlugin` and
`register`.

Install both projects into the same environment:

```powershell
python -m pip install -e C:\path\to\Spotter-Control_v3
python -m pip install -e C:\path\to\openspotter-dots
```

Verify discovery:

```python
from app.core.plugins import PluginRegistry

registry = PluginRegistry()
registry.load_entry_points()
plugin = registry.require("dots")
events = plugin.plan({"params": {"count": 3, "pitch": 2.0}})

assert [event["x"] for event in events] == [0.0, 2.0, 4.0]
```

An entry point may expose a plugin object, class, zero-argument factory, or a
module with `register()`. A zero-argument `register()` factory is recommended:
it keeps import side effects small and matches built-in discovery.

## Manifest and API rules

`PluginManifest` fields have these compatibility meanings:

| Field | Rule |
| --- | --- |
| `id` | Permanent lowercase identifier matching `^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`. Do not rename it after profiles or configs use it. |
| `display_name` | Non-empty operator-facing name; it may change compatibly. |
| `version` | Plugin release version. Semantic Versioning is recommended. |
| `api_version` | Must exactly equal `app.core.plugins.API_VERSION`; the current value is `1`. |
| `description` | Optional human-readable summary. |
| `capabilities` | Unique non-empty metadata strings. They are currently descriptive, not permission grants. |
| `dependencies` | Unique non-empty metadata strings. The registry does not install or resolve them. Declare real Python dependencies in package metadata. |

The entry-point name should equal the manifest ID even though validation is
based on the manifest. Duplicate manifest IDs are rejected; discovery never
silently replaces the first plugin.

The application package version, plugin API version, profile schema, workflow
schema, and firmware contract are independent. A plugin update must not
silently rewrite another compatibility axis.

Plugin API `1` covers the minimal manifest/planner contract and the full
application contract described by this release. Adding an optional structural
capability is compatible; changing a required hook or its semantics requires a
plugin API review and normally an API-version increment. External packages
should also constrain the supported `openspotter-control` release range because
the application protocols are still evolving before a stable `1.0` release.

## Numeric events, never machine commands

`plan(context)` is a geometry/data boundary. Return a deterministic sequence of
plain mappings containing finite numbers, booleans, strings, and stable keys.
Do not return or execute:

- G-code lines or Klipper macros;
- fields such as `gcode`, `command`, `script`, or raw template fragments;
- Moonraker URLs, RPC calls, uploads, or start requests;
- callbacks that touch Tk or hardware; or
- values that depend on current time, unordered iteration, or hidden globals.

Python planners own geometry, volume calculations, limits, refill decisions,
and event order. Named workflow events carry numeric context to
`WorkflowEngine`; the validated workflow document owns machine-command text.

This separation is an architectural and review rule. A third-party package is
ordinary Python, so the registry cannot sandbox malicious code. Install only
trusted plugins and test their source.

## Desktop workspace hooks

An object is selected by `application_plugins()` only when it structurally
satisfies `ApplicationPatternPlugin`. The required hooks are:

| Hook | Contract |
| --- | --- |
| `workspace` | A `WorkspaceSpec` with stable plugin/profile/state keys, GUI attribute names, config filenames, labels, and default colors. |
| `instance_map(gui)` | Return the mutable one-based `{index: editor}` mapping owned by the shell. |
| `resolve_config_path(config_dir, index)` | Select an indexed default or a deterministic fallback. |
| `create_editor(parent, config_dir, index, on_name_changed)` | Construct one editor. Keep planning logic out of the widget class. |
| `serialize_editor(editor)` | Return one canonical JSON-compatible profile entry. |
| `validate_profile_entry(payload, index)` | Reject the wrong root/subsection types and normalize a detached mapping. |
| `restore_profile_entry(editor, payload)` | Restore a validated canonical entry. |
| `persist_editor_defaults(editor, config_dir, index)` | Atomically write flattened editable defaults and return the path. |
| `generate(gui, filepath=None)` | Produce this plugin's artifact through numeric planning, named events, workflow rendering, atomic output, and a sidecar. |
| `capture_runtime_recipes(gui, global_values, workflow)` | On the Tk thread, strictly validate and detach every active recipe into `PatternRecipeSnapshot` records. |
| `generate_runtime(context, recipes, filepath)` | In a worker, generate from `RuntimeGenerationContext` plus detached recipes without reading widgets. |
| `workflow_preview_groups(editor, index)` | Return unindexed `WorkspaceValueGroup` values used to preview workflow variables. |
| `visual_binding_groups(editor, index)` | Return stable indexed groups used by visual-object bindings. |

The editor is expected to expose neutral `get_name()`, `set_name()`,
`get_color()`, `set_color()`, `serialize()`, `restore()`, and
`defaults_dict()` behavior. Grid and spiral retain `get_grid_*` aliases only
for legacy callers.

The runtime hooks are required for every `ApplicationPatternPlugin`, even when
the plugin is intended mainly for saved files. This keeps the machine
controller generic and makes unsupported direct execution fail at plugin
validation/composition rather than after an operator presses Start.

### Fields

Declare plugin inputs with immutable `app.core.schema.Field` objects:

```python
from app.core.schema import Field

DOT_FIELDS = (
    Field("count", "Count", "int", default=1),
    Field("x", "Start X", "mm", default=0.0),
    Field("y", "Start Y", "mm", default=0.0),
    Field("pitch", "Pitch", "mm", default=1.0),
    Field("volume_ul", "Volume", "uL", default=0.0),
    Field(
        "mode",
        "Mode",
        "str",
        default="drop",
        widget="combobox",
        choices=("drop", "continuous"),
    ),
)
```

Keep field keys stable across defaults, editor serialization, profile loading,
planner context, workflow metadata, and visual bindings. Use strict coercion at
execution boundaries; permissive defaulting is for interactive editing only.
`widget` and `choices` are optional presentation hints consumed by
`app.core.ui.forms.create_labels`; business logic must still validate the
selected value.

### Workspace metadata

```python
from app.core.application_patterns import WorkspaceSpec

DOT_WORKSPACE = WorkspaceSpec(
    plugin_id="dots",
    parameter_title="DOT PARAMETERS",
    add_button_text="ADD DOT PATTERN",
    remove_button_text="REMOVE DOT PATTERN",
    notebook_attribute="dot_tabs",
    instance_map_attribute="dot_tab_dict",
    count_attribute="dot_count",
    state_count_key="dot_count",
    profile_key="dot_settings",
    config_filename_template="config_dots_{index}.json",
    fallback_config_filename="config_dots_1.json",
    default_colors=("blue", "orange"),
)
```

Those keys define persisted and shell-facing compatibility. Changing one
requires migration. External plugin defaults are not seeded by
`app.paths.PACKAGED_CONFIG_FILES`; keep immutable defaults in the plugin
package or provide an explicit installation/migration step.

The global persisted key `max_grid_count` is a legacy name. It now means
**Maximum Pattern Count** for each registered plugin workspace; do not create a
second plugin-specific global cap merely to avoid the historical key.

### Workflow contributions

A full plugin may expose `workflow_contribution` from
`app.core.workflow.WorkflowContribution`. Contributions may declare:

- field groups;
- event triggers;
- trigger and job-kind variable scopes;
- derived variable metadata;
- preview context defaults; and
- required custom workflow variables.

Use explicit order values and a `contributor_id` equal to the manifest ID.
Aggregation rejects duplicate ownership and invalid extensions. A contribution
describes data availability only; it must not embed command templates.

When adding a new event, the plugin's event planner calls the shared
`emit_event()` path with numeric overrides. Operators then add or enable the
matching command template in the workflow document. Treat a missing workflow
section as a compatibility/deployment concern, not a reason to hard-code a
fallback command in Python.

### Workflow preview hooks

`workflow_preview_groups()` is a required application hook. It supplies live,
unindexed editor values such as `dots.count` to the workflow editor.
`visual_binding_groups()` similarly supplies stable indexed values such as
`dots.2.x` to visual-object bindings.

Realistic event samples are a separate optional capability. Implement
`app.core.workflow_preview.WorkflowPreviewPlugin` with:

```python
workflow_preview_triggers = frozenset(("dots_start", "dots_drop"))


def enrich_workflow_preview(self, sample):
    if sample.trigger == "dots_drop":
        sample.put("runtime.spot.index", 0)
        sample.put("runtime.spot.x", sample.number("dots.x"))
        sample.put("runtime.spot.y", sample.number("dots.y"))
```

The trigger set declares ownership. Duplicate owners raise
`WorkflowPreviewConflictError`. `WorkflowPreviewSample` is detached and offers
`get`, `put`, `number`, `integer`, `custom_number`, and `select_container`.
Core enriches common rinse values and provides `populate_refill_preview()` for
shared refill arithmetic; the plugin owns its spot and maintenance semantics.
Do not put command text in representative context.

### Canvas preview capability

`CanvasPreviewProvider` is optional. A provider implements:

```python
from app.core.canvas import (
    CanvasPreview,
    MarkerPrimitive,
)


def build_canvas_preview(self, gui, context):
    markers = tuple(
        MarkerPrimitive(
            x=float(point["x"]),
            y=float(point["y"]),
            color="blue",
            volume_ul=float(point["dispense_ul"]),
            z_index=20,
            safety_relevant=True,
        )
        for point in self.plan({"params": {"count": 3}})
    )
    return CanvasPreview(markers=markers)
```

`CanvasPreviewContext` provides:

- detached, top-level read-only `global_values`;
- the active `config_dir`;
- the runtime workflow source; and
- `CanvasPreviewStyle`, a small shell-owned palette for maintenance layers.

Return only `CanvasPreview` with `MarkerPrimitive`, `PolylinePrimitive`,
`LinePrimitive`, and optional hidden `safety_points`. `CanvasPreview.metadata`
is detached and top-level read-only. All points affect fit-to-content, while
acceptance checks include explicit `safety_points` and only primitives whose
`safety_relevant` flag is true. Use `safety_relevant=False` for intentional
maintenance travel outside the spotting acceptance region, not to suppress a
real pattern violation.

The renderer draws lower `z_index` values first, then higher layers. At an
equal z-index, markers, polylines, and lines use a stable type/order tie-break.
A provider exception or wrong return type is isolated and recorded as a
preview warning; it does not stop other plugins from drawing. Plugins without
this capability simply have no main-canvas pattern layer.

## Generation and profile compatibility

A full plugin generator should:

1. snapshot typed editor and common values;
2. call its registered plugin's numeric `plan()` method;
3. validate finite coordinates, volumes, counts, and configured limits;
4. emit named workflow events through shared lifecycle helpers;
5. write the artifact atomically;
6. write a schema-versioned settings sidecar atomically; and
7. return the final artifact path.

Do not start or upload a job from `generate()`. Direct execution belongs to the
machine controller and needs its independent preflight and operator
confirmation.

### Detached direct-run hooks

`capture_runtime_recipes()` runs on the Tk thread. It must:

1. read every widget while thread access is safe;
2. use strict field coercion;
3. validate plugin-specific ranges, counts, modes, containers, and resource
   limits;
4. validate names/colors or other interpolated text;
5. detach the payload from every widget and mutable GUI collection; and
6. return one or more `PatternRecipeSnapshot` values with the plugin ID,
   one-based recipe number, immutable payload, and conservative
   `estimated_work`.

The shared application-pattern module provides:

- `capture_runtime_fields()` for strict schema-ordered widget capture;
- `require_runtime_range()` for readable numeric limits;
- `validate_runtime_container_ids()` for configured container slots;
- `validated_runtime_text()` for non-empty, bounded, control-free metadata;
- `FrozenDict` for shallow immutable mappings;
- `PatternRecipeSnapshot` for plugin-tagged recipes; and
- `RuntimeValueSource`, `RuntimeBooleanSource`, and `runtime_entries()` for
  temporary adapters around older widget-shaped generators.

`generate_runtime(context, recipes, filepath)` runs in a worker. It receives a
`RuntimeGenerationContext` containing the config directory, immutable global
values, and a serialized workflow snapshot. It must never read Tk widgets. It
must generate the exact requested path, write the matching settings sidecar,
and return a truthy path.

The host verifies recipe ownership, applies the total estimated-work and
50-MiB artifact caps, hashes and indexes the artifact, and chooses a
content-addressed Moonraker path. The controller then shows a generic
manifest-derived recipe count plus workflow hash, artifact hash, size, line
count, and destination before the normal artifact/hardware preflights. Upload,
confirmation, and start therefore need no plugin-specific controller branch.

Generation profile schema `3` has the generic form:

```json
{
  "schema_version": 3,
  "global_settings": {},
  "patterns": [
    {
      "plugin_id": "dots",
      "plugin_version": "0.1.0",
      "recipes": []
    }
  ],
  "workflow": {}
}
```

The shell validates each `recipes` entry through the matching registered
plugin, rebuilds all registered workspaces, and calls
`restore_profile_entry()`. Built-in generators also write the legacy
`grid_settings` and `spiral_settings` arrays for schema-version 2 consumers.
New plugins should treat `patterns` as authoritative and keep their canonical
recipe shape backward compatible or provide an explicit migration.

Workspace-state schema `2` stores counts in a generic `patterns` mapping and
retains legacy per-plugin count keys. The shipped unversioned grid/spiral state
seed remains readable and upgrades on the next save.

## Tests required for a plugin

At minimum, test:

- valid and invalid manifests, exact API compatibility, and duplicate IDs;
- entry-point discovery and idempotence;
- deterministic planning from fixed input;
- empty, minimum, maximum, negative, non-finite, and malformed inputs;
- that recursive planner output contains no command-like keys or command text;
- field coercion and stable field keys;
- editor serialize/restore round trips without a display where possible;
- structural profile rejection and migration behavior;
- atomic default and artifact writes;
- workflow contribution aggregation and ownership conflicts;
- workflow-preview trigger ownership and representative context values;
- numeric event order and exact rendered output for a representative job;
- runtime capture detachment, strict validation, estimated-work bounds, and
  worker generation without widgets;
- preview provider return types, read-only context/metadata, z-order, fit
  points, and safety-relevant filtering when used; and
- wheel installation and import from outside both source checkouts.

A useful command-text guard is:

```python
FORBIDDEN_KEYS = {"gcode", "command", "commands", "macro", "script"}


def assert_numeric_event(record):
    assert not (FORBIDDEN_KEYS & set(record))
    for value in record.values():
        if isinstance(value, dict):
            assert_numeric_event(value)
        else:
            assert isinstance(value, (int, float, bool, str, type(None)))
```

Also run the host application's plugin, workflow, generation, profile, and
direct-run integration tests before publishing.

## Deployment compatibility

- Support Python 3.8 or newer while the host package declares that range. Host
  source/wheel CI covers Python 3.8 and 3.12; frozen applications bundle their
  interpreter.
- Use `pathlib.Path` or supplied paths; never depend on the current directory.
- Read immutable plugin resources through package-aware resource APIs.
- Write only to the runtime/config/output locations supplied by the host or an
  explicit plugin-owned user-data location.
- Do not bundle credentials or write API keys to logs.
- Keep imports lightweight. Discovery occurs during application startup and
  workflow initialization.
- Do not access Tk from worker/network threads.
- Build and test a wheel; an editable checkout can hide undeclared resources.
- Pin the supported host/plugin API range in package metadata and publish a new
  plugin version for every compatibility change.

New plugins should import owning modules under `app.core` and avoid legacy
facades such as `app.SpotterFunctions`, `app.gcode_planner`,
`app.input_configs`, `app.grid`, and `app.spiral_grid`.
