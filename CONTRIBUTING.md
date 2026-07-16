# Contributing

OpenSpotter combines safety-sensitive control software with large mechanical
design files. Keep changes narrow, reviewable, and reproducible.

## Branches and commits

- Start from the current reviewed integration branch and use a short-lived
  branch such as `feat/...`, `fix/...`, `refactor/...`, `docs/...`, or
  `release/...`.
- Do not push unrelated cleanup, generated output, credentials, or local
  configuration with a feature.
- Prefer imperative Conventional Commit-style subjects:
  `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `build:`, or `chore:`.
- Check `git status` and the staged diff before every commit. Never discard or
  rewrite another contributor's uncommitted work.

## Required checks

From `OpenSpotter-Syringe/Spotter-Control_v3`:

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m compileall -q app
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
```

Run the visible GUI after changes to interaction, layout, paths, images, or
workflow editing. Motion-related changes also require review of the matching
workflow and Klipper contract plus an elevated, fluid-free physical dry run;
unit tests do not authorize machine motion.

## Core and plugins

- Keep reusable storage, schema, canvas, and G-code behavior in `app/core`.
- Built-in pattern implementations belong in their own package under
  `app/plugins`; core code must not import a concrete pattern plugin.
- Plugins must expose validated metadata, use the supported plugin API, keep
  geometry numeric, and leave machine-command rendering to the workflow layer.
- Add contract, discovery, failure-isolation, generation, and preview tests for
  new plugins. Do not silently replace a registered plugin ID.
- Treat external plugins as executable code and document their supported
  OpenSpotter/plugin API versions.

## Versions and compatibility

- The desktop version lives in `app/version.py`; record user-visible changes in
  `CHANGELOG.md`.
- Profile, workflow, visual-object, plugin API, TCP-coordinate, and Klipper
  contract versions are separate compatibility boundaries. Change them only
  with validation, migration behavior, tests, and release notes.
- Follow `OpenSpotter-Syringe/Spotter-Control_v3/VERSIONING.md` for tags and
  release preparation. Do not move or reuse a published version tag.

## CAD, binaries, and Git LFS

- CAD tools can touch many binary files on open or save. Treat existing dirty
  CAD changes as user-owned, stage explicit paths, and keep software-only
  commits separate from mechanical revisions.
- Do not normalize, regenerate, rename, or delete CAD/vendor files as incidental
  cleanup. Include manufacturing exports only when they belong to the reviewed
  hardware revision.
- The repository does not currently rewrite existing history into Git LFS.
  Never run `git lfs migrate` or add broad LFS rules without maintainer
  agreement, clone-impact review, and a coordinated migration plan.
- Discuss new large binary files before committing them. If LFS is adopted for
  a file type, update `.gitattributes`, CI checkout requirements, release
  instructions, and contributor setup together.

Never commit `config_moonraker.json`, API keys, logs, generated G-code, virtual
environments, or build output.
