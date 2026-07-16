# Versioning and Releases

## Version axes

OpenSpotter uses separate versions for separate compatibility boundaries:

| Boundary | Current value | Purpose |
| --- | --- | --- |
| Desktop package | `0.1.0.dev0` | User-visible application release |
| Pattern plugin API | `1` | Registry, application-workspace, runtime, and optional-capability compatibility |
| Generation profile | schema `3` | Plugin-oriented saved job/profile compatibility |
| Workspace state | schema `2` | Registered plugin counts and startup restoration |
| G-code workflow | schema `1` | Editable workflow document compatibility |
| Visual objects | schema `2` | Canvas object and binding compatibility |
| Moonraker connection settings | schema `1` | Local connection configuration compatibility |
| Klipper desktop contract | `OPENSPOTTER_CONTRACT_V3` | Required remote-control macro set |
| TCP coordinates | version `2` | Saved calibration sign/convention compatibility |

Changing one axis does not silently change another. A package patch release may
retain every schema and firmware contract. A schema or contract change requires
an explicit migration, compatibility check, and release note.

## Desktop version policy

The desktop package follows Semantic Versioning while the public plugin and
storage APIs are still evolving:

- patch: compatible fixes, documentation, packaging, or safety tightening;
- minor: compatible features or new built-in capabilities;
- major: intentionally incompatible public API, profile, or operator workflow
  changes.

Development builds use PEP 440 forms such as `0.1.0.dev0`. Release tags use
`vMAJOR.MINOR.PATCH`, for example `v0.1.0`. The version source of truth is
`app/version.py`; `pyproject.toml` reads it when building metadata.

## Plugin API policy

`app.core.plugins.API_VERSION` is the source of truth for the
`PluginManifest.api_version` field. Discovery requires an exact match; an
incompatible plugin is never silently loaded under a best-effort contract.

API `1` covers:

- the minimal manifest and numeric `plan(context)` registry contract;
- the required `ApplicationPatternPlugin` workspace, profile, saved-generation,
  runtime-capture, and worker-generation hooks;
- typed workflow contribution records; and
- the optional `CanvasPreviewProvider` and `WorkflowPreviewPlugin`
  capabilities described in [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md).

Adding an optional capability or data field with a safe default may remain
compatible. Removing or changing a required hook, changing the meaning of an
existing manifest/recipe field, or accepting previously incompatible behavior
requires an explicit API review and normally a new plugin API version. A
plugin's own `manifest.version` remains independent and should follow Semantic
Versioning.

Because the desktop package is still pre-1.0, external plugins should constrain
both the plugin API and a tested `openspotter-control` package range.

## Profile and state compatibility

Generation profile schema `3` stores a generic `patterns` array containing
plugin IDs, plugin versions, and canonical recipes. Built-in generators retain
the schema-version 2 `grid_settings` and `spiral_settings` arrays during the
migration period, and the loader accepts either representation.

Workspace-state schema `2` stores counts under a generic `patterns` mapping and
also writes each plugin's legacy `state_count_key`. The reader accepts the
shipped unversioned `grid_count`/`spiral_count` seed and upgrades it on the next
save. The persisted `max_grid_count` global key is also retained, but its
current meaning is **Maximum Pattern Count** for each registered workspace.

## Release procedure

1. Create a release branch from the reviewed integration branch.
2. Move relevant entries from `CHANGELOG.md`'s Unreleased section into a dated
   release section.
3. Set a final version in `app/version.py`.
4. Run the complete clean-environment, wheel-install, and standalone checks in
   `DEPLOYMENT.md`.
5. Verify the documented application/workflow/Klipper compatibility set on a
   safe test machine.
6. Commit with `release: vX.Y.Z`.
7. Create an annotated `vX.Y.Z` tag on that exact commit.
8. Publish wheel, source archive, per-OS application artifacts, checksums, and
   release notes.
9. Advance `app/version.py` to the next development version in a follow-up
   commit.

Never reuse or move a published release tag. Correct a bad release with a new
patch version and retain the old artifacts and notes for traceability.
