# Changelog

Notable user-visible changes are recorded here. This project follows Semantic
Versioning for the desktop package and keeps data-schema and firmware-contract
versions separate.

## [Unreleased]

### Added

- A versioned pattern plugin API with validated manifests, deterministic
  built-in discovery, installed `openspotter.patterns` entry points,
  idempotent loading, compatibility checks, and duplicate-ID protection.
- A full application-plugin contract covering workspace metadata, editor
  creation, defaults, profiles, saved generation, strict direct-run capture,
  worker generation, workflow field groups, and visual bindings.
- Separate built-in `app.plugins.grid` and `app.plugins.spiral` packages with
  owned manifests, fields, editors, planners, generation, runtime adapters,
  canvas previews, workflow metadata, and representative workflow previews.
- Typed workflow contributions for plugin-owned field groups, triggers,
  trigger/job scopes, derived variables, context defaults, and required custom
  values, with deterministic conflict detection.
- Optional `WorkflowPreviewPlugin` dispatch so plugins can provide realistic
  representative event values without teaching the workflow editor their
  semantics.
- Optional `CanvasPreviewProvider` support with detached preview context/style,
  immutable marker/polyline/line primitives, hidden safety points, warnings,
  metadata, z-order, and per-primitive acceptance relevance.
- Generic immutable `PatternRecipeSnapshot` and
  `RuntimeGenerationContext` models plus shared strict runtime field, range,
  container, and text validators.
- Schema-version 3 generation profiles with a generic `patterns` array,
  plugin IDs/versions, canonical recipes, and portable G-code filenames.
- Schema-version 2 workspace state with a generic registered-plugin count map.
- Reusable core packages for schemas, schema-driven Tk forms, atomic storage,
  domain/geometry helpers, canvas models, workflow composition, and shared
  G-code lifecycle/profile services.
- PEP 621 package metadata, `openspotter-control` and `python -m app`
  entry points, package data declarations, and Semantic/PEP 440 version
  metadata.
- Source, per-user, portable, and explicit runtime-storage modes; first-run
  default seeding; and opt-in migration from an earlier checkout.
- A PyInstaller standalone-build specification and deployment/release
  documentation for source, wheel, and frozen installations.
- Windows and Ubuntu CI across Python 3.8 and 3.12, including compilation,
  the full test suite, wheel building, and an installed-wheel smoke test
  outside the checkout.
- Architecture-boundary tests that prevent core-to-concrete/shell imports,
  outward dependencies in pure plugin layers, and duplicate implementations in
  legacy facades.
- Contributor, architecture, plugin-development, deployment, versioning, and
  release documentation plus repository text/binary normalization rules.

### Changed

- The main window now builds workspaces, mode selection, add/remove actions,
  state restoration, defaults, profile loading, workflow values, and visual
  bindings from registered application plugins.
- Top-level saved generation now dispatches every non-empty application plugin
  and derives output suffixes from stable plugin IDs.
- Direct Start now delegates strict Tk-thread recipe capture and detached worker
  generation to the selected plugin. Shared runtime code validates ownership,
  total work, artifact size, hashing, line indexing, retention, and remote
  naming without pattern branches.
- Machine confirmation now uses manifest display metadata and generic recipe
  counts while retaining the exact workflow hash, artifact SHA-256, size, line
  count, destination, fresh preflight, upload-without-start, and separate start
  RPC.
- Canvas collection and drawing now combine renderer-neutral results from every
  preview-capable plugin. Fit-to-content, acceptance checking, stable z-order,
  and provider-failure isolation are shell-owned and pattern-neutral.
- Workflow validation/catalog/defaults now aggregate core and registered plugin
  contributions; detailed event previews dispatch optional plugin enrichers.
- The active workflow path now resolves to writable runtime configuration,
  while a separate immutable shipped path is used only as the missing-file
  fallback.
- The field schema now supports widget and choice hints. Global and plugin
  editors share one form builder, including readonly spiral mode/interleave
  choices.
- The legacy `max_grid_count` value is presented and enforced as **Maximum
  Pattern Count** for every registered workspace.
- Grid and spiral field, planning, generation, preview, runtime, and workflow
  ownership moved out of mixed top-level modules into their plugin packages.
- Atomic JSON/text replacement is shared by defaults, state, workflow,
  profiles, visual objects, and local Moonraker settings.
- Packaged application resources are separated from writable operator data;
  installed/frozen applications no longer attempt to mutate package files.
- Resource/config/output/log paths no longer depend on the current working
  directory.
- Local Moonraker credentials remain per-user runtime data, are excluded from
  package artifacts, and retain owner-only permission hardening where the
  platform supports it.

### Compatibility

- `app.grid`, `app.spiral_grid`, `app.grid_gcode`, `app.spiral_gcode`,
  `app.gcode_planner`, and `app.SpotterFunctions` remain export-only
  compatibility facades while new code imports the owning core or plugin
  module. `app.input_configs` retains global fields and compatibility-exports
  plugin-owned fields.
- Built-in schema-version 3 profiles retain `grid_settings` and
  `spiral_settings` arrays for schema-version 2 readers.
- Profile loading accepts generic schema-version 3 patterns and legacy
  per-plugin arrays.
- Workspace state writes the generic schema-version 2 `patterns` mapping plus
  legacy plugin count keys and still reads the shipped unversioned built-in
  state seed.
- `GenerationSnapshot.grids`/`.spirals`, built-in GUI helper names, and
  grid-like editor naming aliases remain available while generic code uses
  plugin-tagged recipes and neutral methods.
